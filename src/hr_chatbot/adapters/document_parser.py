"""Fail-closed parsing for HR-approved text and FAQ snapshots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".json"}
WINDOWS_DEVICES = {
    "AUX",
    "CON",
    "NUL",
    "PRN",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class DocumentRejected(ValueError):
    """The snapshot cannot cross the ingestion trust boundary."""


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    kind: Literal["paragraph", "faq"]
    text: str
    location: str


@dataclass(frozen=True, slots=True)
class ParsedTable:
    location: str
    search_text: str
    markdown: str


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    document: tuple[tuple[str, str], ...]
    blocks: tuple[ParsedBlock, ...]
    tables: tuple[ParsedTable, ...] = ()
    warnings: tuple[str, ...] = ()


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def validate_source_path(path: Path, inbox: Path) -> Path:
    if ".." in path.parts:
        raise DocumentRejected("path_escape")
    suffix = path.suffix.lower()
    device_name = path.name.split(".", 1)[0].upper()
    if suffix not in ALLOWED_SUFFIXES or device_name in WINDOWS_DEVICES:
        raise DocumentRejected("unsupported_path")
    inbox_resolved = inbox.resolve(strict=True)
    try:
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise DocumentRejected("source_missing") from error
    if not resolved.is_relative_to(inbox_resolved):
        raise DocumentRejected("path_escape")
    if path.is_symlink() or _is_reparse_point(path):
        raise DocumentRejected("reparse_point")
    if not resolved.is_file():
        raise DocumentRejected("not_regular_file")
    return resolved


def _decode_utf8(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise DocumentRejected("invalid_encoding") from error
    if "\x00" in text:
        raise DocumentRejected("invalid_text")
    return text


def _parse_txt(path: Path, content: bytes) -> ParsedDocument:
    text = _decode_utf8(content).replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = [part.strip() for part in re.split(r"\n[ \t]*\n+", text) if part.strip()]
    blocks = tuple(
        ParsedBlock("paragraph", paragraph, f"paragraph:{number}")
        for number, paragraph in enumerate(paragraphs, start=1)
    )
    return ParsedDocument((("filename", path.name), ("format", path.suffix.lower()[1:])), blocks)


def _parse_csv(path: Path, content: bytes) -> ParsedDocument:
    try:
        reader = csv.DictReader(io.StringIO(_decode_utf8(content), newline=""))
        if reader.fieldnames != ["question", "answer"]:
            raise DocumentRejected("invalid_faq_schema")
        blocks: list[ParsedBlock] = []
        for number, row in enumerate(reader, start=2):
            question = (row.get("question") or "").strip()
            answer = (row.get("answer") or "").strip()
            if not question or not answer or None in row:
                raise DocumentRejected("invalid_faq_schema")
            blocks.append(
                ParsedBlock("faq", f"질문: {question}\n답변: {answer}", f"row:{number}")
            )
    except csv.Error as error:
        raise DocumentRejected("invalid_faq_schema") from error
    return ParsedDocument((("filename", path.name), ("format", "csv")), tuple(blocks))


def _parse_json(path: Path, content: bytes) -> ParsedDocument:
    try:
        payload = json.loads(_decode_utf8(content))
    except json.JSONDecodeError as error:
        raise DocumentRejected("invalid_json") from error
    if not isinstance(payload, list):
        raise DocumentRejected("invalid_faq_schema")
    blocks: list[ParsedBlock] = []
    for number, item in enumerate(payload, start=1):
        if not isinstance(item, dict) or set(item) != {"question", "answer"}:
            raise DocumentRejected("invalid_faq_schema")
        question, answer = item["question"], item["answer"]
        if not isinstance(question, str) or not isinstance(answer, str):
            raise DocumentRejected("invalid_faq_schema")
        question, answer = question.strip(), answer.strip()
        if not question or not answer:
            raise DocumentRejected("invalid_faq_schema")
        blocks.append(
            ParsedBlock("faq", f"질문: {question}\n답변: {answer}", f"item:{number}")
        )
    return ParsedDocument((("filename", path.name), ("format", "json")), tuple(blocks))


def _parse_bytes(path: Path, content: bytes) -> ParsedDocument:
    parsers = {".txt": _parse_txt, ".md": _parse_txt, ".csv": _parse_csv, ".json": _parse_json}
    parser = parsers.get(path.suffix.lower())
    if parser is None:
        raise DocumentRejected("unsupported_path")
    return parser(path, content)


def parse_document(path: Path) -> ParsedDocument:
    return _parse_bytes(path, path.read_bytes())


def parse_approved_snapshot(
    path: Path,
    inbox: Path,
    expected_sha256: str,
    *,
    max_bytes: int = 50 * 1024 * 1024,
) -> ParsedDocument:
    resolved = validate_source_path(path, inbox)
    with resolved.open("rb") as handle:
        content = handle.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise DocumentRejected("file_too_large")
    if not hmac.compare_digest(hashlib.sha256(content).hexdigest(), expected_sha256.lower()):
        raise DocumentRejected("checksum_mismatch")
    return _parse_bytes(resolved, content)


def _to_payload(parsed: ParsedDocument) -> dict[str, object]:
    return {
        "document": dict(parsed.document),
        "blocks": [
            {"kind": block.kind, "text": block.text, "location": block.location}
            for block in parsed.blocks
        ],
        "tables": [],
        "warnings": list(parsed.warnings),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--inbox", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        parsed = parse_approved_snapshot(args.input, args.inbox, args.sha256)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(_to_payload(parsed), ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(args.output)
    except (DocumentRejected, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
