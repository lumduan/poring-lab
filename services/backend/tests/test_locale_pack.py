"""scripts/locale_pack.py on SYNTHETIC tables generated here (never real client strings)."""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "locale_pack.py"


@pytest.fixture(scope="module")
def lp() -> ModuleType:
    spec = importlib.util.spec_from_file_location("locale_pack", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["locale_pack"] = mod
    spec.loader.exec_module(mod)
    return mod


def write_table(path: Path, lines: list[str], encoding: str) -> Path:
    path.write_bytes("".join(f"{line}#\r\n" for line in lines).encode(encoding))
    return path


# A made-up reference build (ids 0..5) and a source build whose ids are SHIFTED by one: the
# source inserted a line at id 1, so only the English tables can line the two up.
REF_KO = ["확인", "취소", "%s 님이 접속했습니다", "", "가방", "%d 제니"]
REF_EN = ["OK", "Cancel", "%s has logged in", "", "Inventory", "%d Zeny"]
SRC_EN = ["OK", "(source-only line)", "Cancel", "%s has logged in", "", "Bag", "%d Zeny"]
# Synthetic Thai on purpose: real UI words would equal real pack strings, and the pre-commit
# fingerprint guard would then refuse this file.
SRC_TH = ["กขคง", "บรรทัดสังเคราะห์", "ทดสอบสองสาม", "%s ข้อความทดสอบสี่", "", "ทดสอบห้า", "%d หน่วยทดสอบ"]


def test_key_rule_is_sha1_of_the_normalised_korean(lp: ModuleType) -> None:
    expected = "msg.k" + hashlib.sha1("확인".encode()).hexdigest()[:8]
    assert lp.message_key("확인#") == expected
    assert lp.message_key("확인\r\n#") == lp.message_key("확인\n")  # CRLF -> LF, one '#'
    decomposed = "한"  # 한 as conjoining jamo; NFC composes it
    assert lp.message_key(decomposed) == lp.message_key("한")
    assert lp.message_key("") is None and lp.message_key("#") is None
    assert lp.message_key("확인 ") != lp.message_key("확인")  # spaces are part of the message


def test_placeholder_signature(lp: ModuleType) -> None:
    assert lp.placeholder_signature("%s has %d of %.2f%%") == ("s", "d", "f")
    assert lp.placeholder_signature("%1$s %%") == ("s",)
    assert lp.placeholder_signature("no placeholders") == ()


def test_key_collision_stops_the_build(lp: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lp, "message_key", lambda text: "msg.k00000000" if text else None)
    with pytest.raises(lp.PackError, match="collision"):
        lp.key_index(["a", "b"])
    assert lp.key_index(["a", "a"]) == {"msg.k00000000": [0, 1]}  # same text: one key, two ids


def test_alignment_through_the_source_builds_english(lp: ModuleType) -> None:
    norm = [lp.normalise(x) for x in REF_KO]
    result = lp.align(norm, REF_EN, SRC_TH, SRC_EN)
    texts = {k: v["text"] for k, v in result.messages.items()}
    assert texts[lp.message_key("취소")] == "ทดสอบสองสาม"  # id 1 -> source id 2, via "Cancel"
    assert result.messages[lp.message_key("%s 님이 접속했습니다")]["source_ids"] == [3]
    assert lp.message_key("가방") not in texts  # EN differs and same id is contradicted
    assert (result.exact_en, result.index_signature, result.unmatched) == (4, 0, 1)


def test_same_id_fallback_needs_matching_placeholders(lp: ModuleType) -> None:
    norm = [lp.normalise(x) for x in REF_KO]
    # id 2 lost its %s
    source = ["กขคง", "ทดสอบสองสาม", "ข้อความทดสอบสี่", "", "ทดสอบห้า", "%d หน่วยทดสอบ"]
    result = lp.align(norm, REF_EN, source, None)
    assert result.messages[lp.message_key("가방")]["confidence"] == "index_signature"
    assert lp.message_key("%s 님이 접속했습니다") not in result.messages
    assert (result.index_signature, result.unmatched) == (4, 1)


def build_args(lp: ModuleType, tmp_path: Path, out: Path) -> list[str]:
    ref = write_table(tmp_path / "kor.txt", REF_KO, "cp949")
    en = write_table(tmp_path / "en.txt", REF_EN, "cp1252")
    src_en = write_table(tmp_path / "src_en.txt", SRC_EN, "cp1252")
    src_dir = tmp_path / "thai-client" / "data"
    src_dir.mkdir(parents=True)
    write_table(src_dir / "msgStringTable.txt", SRC_TH, "cp874")
    items = tmp_path / "items.json"
    items.write_text(json.dumps({"501": "ไอเท็มสังเคราะห์"}), encoding="utf-8")  # made up
    return [
        "build", "--lang", "th", "--source", str(tmp_path / "thai-client"),
        "--reference", str(ref), "--en", str(en), "--source-en", str(src_en),
        "--out", str(out), "--client-version", "synthetic-th-1", "--font", "Tahoma",
        "--source-desc", "synthetic test tables", "--table", f"items={items}",
        "--fingerprints", str(tmp_path / "fp.txt"),
    ]  # fmt: skip


def test_build_writes_a_valid_pack_and_fingerprints(
    lp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "packs" / "th"
    assert lp.main(build_args(lp, tmp_path, out)) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["coverage"]["covered_keys"] == 4 and report["coverage"]["reference_keys"] == 5
    assert "ทดสอบสองสาม" not in json.dumps(report, ensure_ascii=False)  # counts only, never text
    manifest = json.loads((out / "locale-pack.json").read_text(encoding="utf-8"))
    assert manifest["language"] == "th" and manifest["encoding"] == "cp874"
    assert manifest["tables"] == {"items": "tables/items.json"}
    assert (out / "install" / "data" / "msgstringtable.txt").read_bytes() == (
        tmp_path / "thai-client" / "data" / "msgStringTable.txt"
    ).read_bytes()
    msg = json.loads((out / "msg.json").read_text(encoding="utf-8"))
    assert set(msg["index"]) == {"reference", "synthetic-th-1"}
    assert lp.check(out) == []
    fps = set((tmp_path / "fp.txt").read_text().split())
    assert lp.fingerprint("ทดสอบสองสาม") in fps and lp.fingerprint("ไอเท็มสังเคราะห์") in fps
    assert lp.fingerprint("กขคง") is None  # 4 characters: too short to identify anything

    (out / "msg.json").write_text("{}", encoding="utf-8")
    assert any("hash mismatch" in p or "messages" in p for p in lp.check(out))


def test_build_refuses_the_repo_and_a_used_directory(lp: ModuleType, tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    assert lp.main(build_args(lp, tmp_path, repo / "locale-packs" / "th")) == 2
    assert not (repo / "locale-packs").exists()
    used = tmp_path / "used"
    used.mkdir()
    (used / "x").write_text("x")
    with pytest.raises(lp.PackError, match="not empty"):
        lp.build(argparse.Namespace(out=used))  # an allowed place, but not a fresh directory


def test_keys_command_prints_hashes_only(
    lp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ref = write_table(tmp_path / "kor.txt", REF_KO, "cp949")
    assert lp.main(["keys", "--source", str(ref)]) == 0
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert len(doc["keys"]) == 5 and "확인" not in out


# --source-ref (2026-10-03): the source build's OWN table in the reference's language -- e.g. the
# table the Thai client's exe embeds -- lines the two id spaces up by equal text.
SRC_REF = ["확인", "(source-only)", "취소", "%s 님이 접속했습니다", "", "다른 가방", "%d 제니"]


def test_exact_ref_lines_up_shifted_ids_by_equal_reference_text(lp: ModuleType) -> None:
    norm = [lp.normalise(x) for x in REF_KO]
    ref = [lp.normalise(x) for x in SRC_REF]
    result = lp.align(norm, REF_EN, SRC_TH, None, ref)
    texts = {k: v["text"] for k, v in result.messages.items()}
    assert texts[lp.message_key("취소")] == "ทดสอบสองสาม"  # ref id 1 -> source id 2
    assert result.messages[lp.message_key("%d 제니")]["source_ids"] == [6]
    assert result.messages[lp.message_key("확인")]["confidence"] == "exact_ref"
    # 가방 (id 4): the source's own table says id 4 is something else -> no same-id guess
    assert lp.message_key("가방") not in texts
    assert (result.exact_ref, result.exact_en, result.index_signature) == (4, 0, 0)
    assert result.unmatched == 1


def test_reindex_writes_the_reference_id_order_with_english_fallback(
    lp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "packs" / "th"
    args = build_args(lp, tmp_path, out)
    src_ref = write_table(tmp_path / "src_ref.txt", SRC_REF, "cp949")
    assert lp.main([*args, "--source-ref", str(src_ref), "--reindex"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["coverage"]["reindexed"] == {
        "lines": 6, "translated": 4, "english": 1, "empty": 1, "unencodable": 0,
    }  # fmt: skip
    assert report["coverage"]["exact_ref"] == 4 and report["coverage"]["source_ref_lines"] == 7
    lines = (out / "install" / "data" / "msgstringtable.txt").read_bytes().split(b"\r\n")
    assert lines[:6] == [
        "กขคง#".encode("cp874"),
        "ทดสอบสองสาม#".encode("cp874"),  # the source's id 2, now at the reference's id 1
        "%s ข้อความทดสอบสี่#".encode("cp874"),
        b"#",
        b"Inventory#",  # not aligned: the client keeps our English at its own id
        "%d หน่วยทดสอบ#".encode("cp874"),
    ]
    assert lp.check(out) == []


def test_untranslated_placeholders_keep_our_english(
    lp: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Thai table writes "no msg" for an untranslated id (2026-10-03: 769 of 3,970): it must
    never reach the client as text, and the reference's English stays at that id."""
    ref = write_table(tmp_path / "kor.txt", REF_KO, "cp949")
    en = write_table(tmp_path / "en.txt", REF_EN, "cp1252")
    src = ["กขคง", "No Msg", "%s ข้อความทดสอบสี่", "", "no msg", "%d หน่วยทดสอบ"]
    src_file = write_table(tmp_path / "th.txt", src, "cp874")
    out = tmp_path / "packs" / "th"
    argv = [
        "build", "--lang", "th", "--source", str(src_file), "--reference", str(ref),
        "--en", str(en), "--out", str(out), "--reindex", "--source-untranslated", "no msg",
        "--fingerprints", str(tmp_path / "fp.txt"),
    ]  # fmt: skip
    assert lp.main(argv) == 0
    coverage = json.loads(capsys.readouterr().out)["coverage"]
    assert coverage["source_untranslated"] == 2 and coverage["index_signature"] == 3
    lines = (out / "install" / "data" / "msgstringtable.txt").read_bytes().split(b"\r\n")
    assert lines[1] == b"Cancel#" and lines[4] == b"Inventory#"  # never "no msg"
    assert b"no msg" not in (out / "msg.json").read_bytes().lower()
