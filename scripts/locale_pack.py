#!/usr/bin/env python3
"""Locale packs: build, key and check them (ADR-0012, "Locale-agnostic UI"). Stdlib only.

The bot thinks in canonical KEYS; the text of one language lives in a LOCALE PACK built from the
developer's own client data. Only this builder and the schema below are committed -- a pack's
contents (client strings, aligned tables, install files) NEVER are (CLAUDE.md rule 4,
.gitignore, .githooks/pre-commit).

    locale_pack.py keys --source KOR_TABLE [--encoding cp949] [--version LABEL] [--out FILE]
        The canonical key index of a msgstringtable: key -> message ids. Keys are hashes, so the
        index holds no client text.
    locale_pack.py build --lang th --source SRC --reference KOR --en EN [--source-en EN_SRC]
                         [--source-ref SRC_REF] [--reindex]
                         --out DIR [--client-version V] [--font F] [--source-desc TEXT]
                         [--install DIR] [--table NAME=JSON ...] [--fingerprints FILE]
        Align a language's table to the canonical keys and write the pack to DIR, which must be
        OUTSIDE this git repository (the NAS locale-packs/<lang>/, or /dev/shm). Prints coverage
        counts only, never pack strings.
    locale_pack.py check PACK
        Validate a pack against the schema and its file hashes.

Tables are msgstringtable-style text: one message per line, each ending in '#'; message id = line
number - 1. Encodings: --source-encoding defaults by language (th cp874, en cp1252, ko cp949).

CANONICAL MESSAGE KEY = "msg.k" + the first 8 hex digits of sha1(utf-8 of the normalised KOREAN
source string). The Korean text of the reference client is the one thing every translation was made
from, so the key survives every client version and every language. Normalisation (normalise()):
  1. CRLF and CR -> LF;  2. strip ONE trailing '#' (the table's terminator);  3. Unicode NFC.
Nothing else: spaces and punctuation are part of the message. Empty strings get no key. Two
different strings with the same 8 hex digits stop the build (no silent renaming: keys must be
stable).

Alignment of the SOURCE language (e.g. Thai) to the reference ids, per reference message:
  exact_ref        the source build's own table in the REFERENCE's language (--source-ref, e.g.
                   the table the Thai client's exe embeds, extracted by msgtable_extract.py) has
                   the SAME text as the reference at source id i  ->  the source text at i. Both
                   tables come from Gravity's own builds, so equal text is the same message.
  exact_en         the source build's English table (--source-en) has the SAME English text as
                   ours at source id i  ->  the source text at i. Highest confidence.
  index_signature  no evidence against the same id (neither --source-en nor --source-ref says
                   otherwise there) AND the %-placeholder signature of the source line equals the
                   Korean one's.
  unmatched        otherwise (also when --source-en contradicts the same id).
Ambiguous English matches (several different source texts) prefer the same id, else stay
unmatched and are counted as ambiguous.

Pack layout (schema 1):
  locale-pack.json  manifest: language, client version, source description, font, encoding,
                    key rule, coverage, sha256 of every file
  msg.json          {"messages": {key: {text, confidence, source_ids}},
                     "index": {<reference version>: {key: [ids]}, <client version>: {key: [ids]}}}
  tables/NAME.json  optional {id: text} tables (items, skills) keyed by their own numeric ids
  install/...       files to place in the client: the source msgstringtable as data/... (bytes
                    unchanged), or with --reindex a msgstringtable in the REFERENCE's id order
                    (the client the pack installs into): the aligned text where one was found,
                    else the reference's English line, in the source encoding; and --install
Fingerprints: sha256 of every pack string of >= 6 characters (fingerprint()) is appended to
~/.cache/poring-lab/pack-fingerprints.txt (or $PORING_PACK_FINGERPRINTS), which the pre-commit
hook uses to refuse a commit that carries one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = 1
KEY_PREFIX = "msg.k"
KEY_HEX = 8
KEY_RE = re.compile(r"^msg\.k[0-9a-f]{8}$")
CONFIDENCE = ("exact_ref", "exact_en", "index_signature")
DEFAULT_ENCODING = {"th": "cp874", "en": "cp1252", "ko": "cp949"}
FINGERPRINT_MIN = 6
REPO = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(
    r"%(?:\d+\$)?[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|L|z|j|t|I64)?([diouxXeEfgGcsSp])"
)


class PackError(Exception):
    """A pack that must not be built or does not validate."""


def normalise(text: str) -> str:
    """The canonical form a key is computed from (see the module doc)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.removesuffix("#")
    return unicodedata.normalize("NFC", text)


def message_key(korean: str) -> str | None:
    norm = normalise(korean)
    if not norm:
        return None
    return KEY_PREFIX + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:KEY_HEX]


def fingerprint(text: str) -> str | None:
    """sha256 of a pack string for the pre-commit hook (which repeats this rule), or None when it
    is too short to identify anything."""
    norm = normalise(text).strip()
    if len(norm) < FINGERPRINT_MIN:
        return None
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def placeholder_signature(text: str) -> tuple[str, ...]:
    """The printf conversions in order ("%%" is literal): a translation must keep them."""
    return tuple(PLACEHOLDER.findall(text.replace("%%", "")))


def read_table(path: Path, encoding: str) -> list[str]:
    """One message per line, '#'-terminated; returns normalised strings, id = list index."""
    text = path.read_bytes().decode(encoding, errors="replace")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [normalise(line) for line in lines]


def find_table(source: Path) -> Path:
    """A table file, or the first msgstringtable.txt (any case) under a directory."""
    if source.is_file():
        return source
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.name.lower() == "msgstringtable.txt":
            return path
    raise PackError(f"no msgstringtable.txt under {source}")


def key_index(korean: list[str]) -> dict[str, list[int]]:
    """key -> message ids of a Korean table; stops on a hash collision between different texts."""
    index: dict[str, list[int]] = {}
    text_of: dict[str, str] = {}
    for i, text in enumerate(korean):
        key = message_key(text)
        if key is None:
            continue
        if key in text_of and text_of[key] != text:
            raise PackError(
                f"key collision: {key} for ids {index[key][0]} and {i} (different texts); "
                "raise KEY_HEX for the whole key space rather than renaming one key"
            )
        text_of[key] = text
        index.setdefault(key, []).append(i)
    return index


def outside_repo(path: Path, what: str) -> Path:
    resolved = path.resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise PackError(
            f"refusing {what} inside the git repository ({resolved}): packs never live there"
        )
    return resolved


@dataclass
class Alignment:
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    exact_ref: int = 0
    exact_en: int = 0
    index_signature: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    conflicts: int = 0


def _by_text(table: list[str] | None) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, text in enumerate(table or []):
        if text:
            out.setdefault(text, []).append(i)
    return out


def align(
    reference_ko: list[str],
    reference_en: list[str],
    source: list[str],
    source_en: list[str] | None,
    source_ref: list[str] | None = None,
) -> Alignment:
    """Per reference message id: the source text and how it was found (module doc)."""
    by_en = _by_text(source_en)
    by_ref = _by_text(source_ref)
    result = Alignment()
    for j, korean in enumerate(reference_ko):
        key = message_key(korean)
        if key is None:
            continue
        found: tuple[str, int, str] | None = None  # (text, source id, confidence)
        same = [i for i in by_ref.get(korean, []) if i < len(source) and source[i]]
        if same:
            texts = {source[i] for i in same}
            if len(texts) == 1:
                found = (source[same[0]], same[0], "exact_ref")
            elif j in same:
                found = (source[j], j, "exact_ref")
            else:
                result.ambiguous += 1
        english = reference_en[j] if j < len(reference_en) else ""
        candidates = [i for i in by_en.get(english, []) if i < len(source) and source[i]]
        if found is None and english and candidates:
            texts = {source[i] for i in candidates}
            if len(texts) == 1:
                found = (source[candidates[0]], candidates[0], "exact_en")
            elif j in candidates:
                found = (source[j], j, "exact_en")
            else:
                result.ambiguous += 1
        if found is None:
            contradicted = (
                source_en is not None and j < len(source_en) and source_en[j] != ""
                and source_en[j] != english
            ) or (
                source_ref is not None and j < len(source_ref) and source_ref[j] != ""
                and source_ref[j] != korean
            )  # fmt: skip
            if (
                not contradicted
                and j < len(source)
                and source[j]
                and placeholder_signature(source[j]) == placeholder_signature(korean)
            ):
                found = (source[j], j, "index_signature")
        if found is None:
            result.unmatched += 1
            continue
        text, source_id, confidence = found
        setattr(result, confidence, getattr(result, confidence) + 1)
        entry = result.messages.get(key)
        if entry is None:
            result.messages[key] = {
                "text": text,
                "confidence": confidence,
                "source_ids": [source_id],
            }
        elif entry["text"] != text:
            result.conflicts += 1  # the same Korean text translated two ways: keep the first
        elif source_id not in entry["source_ids"]:
            entry["source_ids"].append(source_id)
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint_file(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("PORING_PACK_FINGERPRINTS")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "poring-lab" / "pack-fingerprints.txt"


def write_fingerprints(path: Path, texts: Iterable[str]) -> int:
    path = outside_repo(path, "the fingerprint list")
    new = {fp for fp in (fingerprint(t) for t in texts) if fp}
    old = set(path.read_text().split()) if path.exists() else set()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(f"{fp}\n" for fp in sorted(old | new)))
    tmp.replace(path)
    return len(new - old)


def build(a: argparse.Namespace) -> dict[str, Any]:
    out = outside_repo(a.out, "--out")
    if out.exists() and any(out.iterdir()):
        raise PackError(f"--out {out} is not empty: build into a fresh directory")
    src_enc = a.source_encoding or DEFAULT_ENCODING.get(a.lang, "utf-8")
    source_table = find_table(a.source)
    reference_ko = read_table(a.reference, a.reference_encoding)
    reference_en = read_table(a.en, a.en_encoding)
    source = read_table(source_table, src_enc)
    source_en = read_table(a.source_en, a.en_encoding) if a.source_en else None
    ref_enc = a.source_ref_encoding or a.reference_encoding
    source_ref = read_table(a.source_ref, ref_enc) if a.source_ref else None
    ref_index = key_index(reference_ko)
    result = align(reference_ko, reference_en, source, source_en, source_ref)

    out.mkdir(parents=True, exist_ok=True)
    install = out / "install"
    (install / "data").mkdir(parents=True)
    reindex_counts: dict[str, int] | None = None
    if a.reindex:
        newline = b"\r\n" if b"\r\n" in source_table.read_bytes() else b"\n"
        body, reindex_counts = reindexed(reference_ko, reference_en, result, src_enc, newline)
        (install / "data" / "msgstringtable.txt").write_bytes(body)
    else:
        shutil.copyfile(source_table, install / "data" / "msgstringtable.txt")  # bytes unchanged
    if a.install:
        shutil.copytree(a.install, install, dirs_exist_ok=True)
    tables: dict[str, str] = {}
    table_texts: list[str] = []
    for spec in a.table or []:
        name, _, src = spec.partition("=")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not src:
            raise PackError(f"--table wants NAME=FILE.json, got {spec!r}")
        data = json.loads(Path(src).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not all(
            isinstance(v, str) and str(k).isdigit() for k, v in data.items()
        ):
            raise PackError(f"--table {name}: expected {{numeric id: text}}")
        (out / "tables").mkdir(exist_ok=True)
        (out / "tables" / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8"
        )
        tables[name] = f"tables/{name}.json"
        table_texts.extend(data.values())

    source_index: dict[str, list[int]] = {}
    for key, entry in result.messages.items():
        source_index[key] = sorted(entry["source_ids"])
    msg = {
        "schema": SCHEMA,
        "lang": a.lang,
        "messages": dict(sorted(result.messages.items())),
        "index": {a.reference_version: ref_index, a.client_version: source_index},
    }
    (out / "msg.json").write_text(json.dumps(msg, ensure_ascii=False, indent=1), encoding="utf-8")
    keys = len(ref_index)
    coverage = {
        "reference_lines": len(reference_ko),
        "reference_keys": keys,
        "covered_keys": len(result.messages),
        "covered_share": round(len(result.messages) / keys, 4) if keys else 0.0,
        "exact_ref": result.exact_ref,
        "exact_en": result.exact_en,
        "index_signature": result.index_signature,
        "unmatched": result.unmatched,
        "ambiguous": result.ambiguous,
        "conflicts": result.conflicts,
        "source_lines": len(source),
        "source_ref_lines": len(source_ref) if source_ref is not None else None,
        "reindexed": reindex_counts,
    }
    files = {str(p.relative_to(out)): sha256_file(p) for p in sorted(out.rglob("*")) if p.is_file()}
    manifest = {
        "schema": SCHEMA,
        "kind": "poring-lab locale pack",
        "language": a.lang,
        "client_version": a.client_version,
        "reference_version": a.reference_version,
        "source": a.source_desc,
        "font": a.font,
        "encoding": src_enc,
        "key_rule": "msg.k + sha1(utf-8(NFC(text minus one trailing '#', CRLF->LF)))[:8]",
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "builder": "scripts/locale_pack.py",
        "coverage": coverage,
        "tables": tables,
        "files": files,
    }
    (out / "locale-pack.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    texts = [e["text"] for e in result.messages.values()] + source + table_texts
    added = write_fingerprints(fingerprint_file(a.fingerprints), texts)
    return {"out": str(out), "coverage": coverage, "fingerprints_added": added}


def reindexed(
    reference: list[str],
    reference_en: list[str],
    result: Alignment,
    encoding: str,
    newline: bytes,
) -> tuple[bytes, dict[str, int]]:
    """A msgstringtable in the REFERENCE's id order (the client the pack installs into): the
    aligned text where one was found, else the reference's English line. Counts only out."""
    counts = {"lines": 0, "translated": 0, "english": 0, "empty": 0, "unencodable": 0}
    lines: list[bytes] = []
    for j, text in enumerate(reference):
        key = message_key(text)
        entry = result.messages.get(key) if key else None
        if entry is not None:
            line, kind = entry["text"], "translated"
        else:
            line = reference_en[j] if j < len(reference_en) else ""
            kind = "english" if line else "empty"
        try:
            raw = line.encode(encoding)
        except UnicodeEncodeError:
            raw = line.encode(encoding, errors="replace")
            counts["unencodable"] += 1
        counts[kind] += 1
        counts["lines"] += 1
        lines.append(raw + b"#" + newline)
    return b"".join(lines), counts


def check(pack: Path) -> list[str]:
    """Problems with a pack (empty = valid)."""
    problems: list[str] = []
    try:
        manifest = json.loads((pack / "locale-pack.json").read_text(encoding="utf-8"))
        msg = json.loads((pack / "msg.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"unreadable pack: {exc}"]
    for field_name, kind in (
        ("schema", int), ("language", str), ("client_version", str), ("reference_version", str),
        ("source", str), ("font", str), ("encoding", str), ("key_rule", str),
        ("coverage", dict), ("tables", dict), ("files", dict),
    ):  # fmt: skip
        if not isinstance(manifest.get(field_name), kind):
            problems.append(f"locale-pack.json: {field_name} missing or not {kind.__name__}")
    if manifest.get("schema") != SCHEMA:
        problems.append(f"locale-pack.json: schema {manifest.get('schema')!r} != {SCHEMA}")
    if msg.get("lang") != manifest.get("language"):
        problems.append("msg.json lang differs from the manifest's language")
    messages = msg.get("messages")
    if not isinstance(messages, dict):
        return [*problems, "msg.json: messages missing"]
    for key, entry in messages.items():
        if not KEY_RE.match(key):
            problems.append(f"msg.json: bad key {key!r}")
        elif not (
            isinstance(entry, dict)
            and isinstance(entry.get("text"), str)
            and entry.get("confidence") in CONFIDENCE
            and isinstance(entry.get("source_ids"), list)
        ):
            problems.append(f"msg.json: bad entry for {key}")
    index = msg.get("index")
    if not isinstance(index, dict) or not all(
        isinstance(v, dict) and all(KEY_RE.match(k) for k in v) for v in index.values()
    ):
        problems.append("msg.json: index must map version -> {key: [ids]}")
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    for rel, digest in files.items():
        path = pack / rel
        if not path.is_file():
            problems.append(f"missing file {rel}")
        elif sha256_file(path) != digest:
            problems.append(f"hash mismatch {rel}")
    coverage = manifest.get("coverage") if isinstance(manifest.get("coverage"), dict) else {}
    if coverage.get("covered_keys") != len(messages):
        problems.append("coverage.covered_keys does not match msg.json")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keys")
    k.add_argument("--source", type=Path, required=True, help="the Korean reference table")
    k.add_argument("--encoding", default="cp949")
    k.add_argument("--version", default="reference")
    k.add_argument("--out", type=Path)
    b = sub.add_parser("build")
    b.add_argument("--lang", required=True)
    b.add_argument("--source", type=Path, required=True, help="table file, or a dir holding one")
    b.add_argument("--source-encoding")
    b.add_argument("--reference", type=Path, required=True, help="Korean table of the reference")
    b.add_argument("--reference-encoding", default="cp949")
    b.add_argument("--reference-version", default="reference")
    b.add_argument("--en", type=Path, required=True, help="English table of the reference build")
    b.add_argument("--source-en", type=Path, help="English table of the SOURCE build")
    b.add_argument(
        "--source-ref", type=Path,
        help="the SOURCE build's own table in the reference's language (e.g. its exe's)",
    )  # fmt: skip
    b.add_argument("--source-ref-encoding", help="default: --reference-encoding")
    b.add_argument(
        "--reindex", action="store_true",
        help="install/ msgstringtable in the reference's id order (aligned text, else English)",
    )  # fmt: skip
    b.add_argument("--en-encoding", default="cp1252")
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--client-version", default="unknown")
    b.add_argument("--source-desc", default="")
    b.add_argument("--font", default="")
    b.add_argument("--install", type=Path, help="a tree copied into install/")
    b.add_argument("--table", action="append", metavar="NAME=FILE.json")
    b.add_argument("--fingerprints", type=Path)
    c = sub.add_parser("check")
    c.add_argument("pack", type=Path)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "keys":
            index = key_index(read_table(a.source, a.encoding))
            doc = {"version": a.version, "keys": index}
            text = json.dumps(doc, indent=1, sort_keys=True)
            if a.out:
                outside_repo(a.out, "--out").write_text(text)
                print(json.dumps({"out": str(a.out), "keys": len(index)}))
            else:
                print(text)
        elif a.cmd == "build":
            print(json.dumps(build(a), indent=1))
        else:
            problems = check(a.pack)
            for p in problems:
                print(p, file=sys.stderr)
            print("valid" if not problems else f"{len(problems)} problem(s)")
            return 0 if not problems else 1
    except PackError as exc:
        print(f"locale_pack: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
