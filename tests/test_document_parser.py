from __future__ import annotations

import inspect
import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest

from hr_chatbot.adapters import document_parser


def test_runtime_parser_has_no_rich_document_or_process_dependencies() -> None:
    source = inspect.getsource(document_parser)

    assert "pdfplumber" not in source
    assert "from docx" not in source
    assert "subprocess" not in source
    assert "socket" not in source


@pytest.mark.parametrize(
    "name", ["policy.pdf", "policy.docx", "snapshot.html", "evil.docm", "CON.txt"]
)
def test_rejects_non_snapshot_formats_and_devices(name: str, tmp_path: Path) -> None:
    with pytest.raises(document_parser.DocumentRejected, match="unsupported_path"):
        document_parser.validate_source_path(tmp_path / name, tmp_path)


def test_rejects_relative_escape_before_resolving(tmp_path: Path) -> None:
    with pytest.raises(document_parser.DocumentRejected, match="path_escape"):
        document_parser.validate_source_path(tmp_path / ".." / "escape.txt", tmp_path)


def test_txt_snapshot_is_split_into_searchable_paragraphs(tmp_path: Path) -> None:
    source = tmp_path / "policy.txt"
    source.write_text("연차는 연 15일입니다.\n\n신청은 그룹웨어에서 합니다.\n", encoding="utf-8")

    parsed = document_parser.parse_document(source)

    assert [block.text for block in parsed.blocks] == [
        "연차는 연 15일입니다.",
        "신청은 그룹웨어에서 합니다.",
    ]
    assert [block.location for block in parsed.blocks] == ["paragraph:1", "paragraph:2"]


def test_md_snapshot_is_plain_text_with_md_format_metadata(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text(
        "# 연차 정책\n\n[사내 규정](https://example.invalid)은 링크 문자열입니다.\n",
        encoding="utf-8",
    )

    parsed = document_parser.parse_approved_snapshot(
        source, tmp_path, sha256(source.read_bytes()).hexdigest()
    )

    assert dict(parsed.document) == {"filename": "policy.md", "format": "md"}
    assert [block.text for block in parsed.blocks] == [
        "# 연차 정책",
        "[사내 규정](https://example.invalid)은 링크 문자열입니다.",
    ]
    assert [block.location for block in parsed.blocks] == ["paragraph:1", "paragraph:2"]


def test_approved_snapshot_requires_matching_checksum(tmp_path: Path) -> None:
    source = tmp_path / "policy.txt"
    source.write_text("연차 정책", encoding="utf-8")

    with pytest.raises(document_parser.DocumentRejected, match="checksum_mismatch"):
        document_parser.parse_approved_snapshot(source, tmp_path, "0" * 64)

    parsed = document_parser.parse_approved_snapshot(
        source, tmp_path, sha256(source.read_bytes()).hexdigest()
    )
    assert parsed.blocks[0].text == "연차 정책"


@pytest.mark.parametrize(
    ("name", "content", "expected_text"),
    [
        ("policy.txt", "연차 정책", "연차 정책"),
        ("policy.md", "# 연차 정책", "# 연차 정책"),
        ("faq.csv", "question,answer\n연차는?,규정 참고\n", "질문: 연차는?\n답변: 규정 참고"),
        (
            "faq.json",
            '[{"question":"연차는?","answer":"규정 참고"}]',
            "질문: 연차는?\n답변: 규정 참고",
        ),
    ],
)
def test_approved_snapshot_reads_source_bytes_only_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    content: str,
    expected_text: str,
) -> None:
    source = tmp_path / name
    source.write_text(content, encoding="utf-8")
    expected_sha256 = sha256(source.read_bytes()).hexdigest()
    original_open = Path.open
    source_opens = 0

    def counting_open(path: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal source_opens
        if path == source:
            source_opens += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    parsed = document_parser.parse_approved_snapshot(source, tmp_path, expected_sha256)

    assert parsed.blocks[0].text == expected_text
    assert source_opens == 1


def test_txt_snapshot_rejects_non_utf8_and_nul(tmp_path: Path) -> None:
    non_utf8 = tmp_path / "legacy.txt"
    non_utf8.write_bytes(b"\xff\xfe")
    with pytest.raises(document_parser.DocumentRejected, match="invalid_encoding"):
        document_parser.parse_document(non_utf8)

    nul = tmp_path / "control.txt"
    nul.write_bytes(b"policy\x00hidden")
    with pytest.raises(document_parser.DocumentRejected, match="invalid_text"):
        document_parser.parse_document(nul)


def test_csv_faq_is_parsed_as_searchable_blocks(tmp_path: Path) -> None:
    source = tmp_path / "faq.csv"
    source.write_text("question,answer\n연차는?,연차 규정을 확인하세요.\n", encoding="utf-8")

    parsed = document_parser.parse_document(source)

    assert parsed.blocks[0].text == "질문: 연차는?\n답변: 연차 규정을 확인하세요."
    assert parsed.blocks[0].location == "row:2"


def test_csv_faq_rejects_inline_policy_subject_for_sidecar_mapping(tmp_path: Path) -> None:
    source = tmp_path / "faq.csv"
    source.write_text(
        "question,answer,policy_subject\n연차는?,규정 참고,annual_leave_days\n",
        encoding="utf-8",
    )

    with pytest.raises(document_parser.DocumentRejected, match="invalid_faq_schema"):
        document_parser.parse_document(source)


def test_json_faq_rejects_unknown_fields(tmp_path: Path) -> None:
    source = tmp_path / "faq.json"
    source.write_text(
        json.dumps([{"question": "연차는?", "answer": "규정 참고", "extra": True}]),
        encoding="utf-8",
    )

    with pytest.raises(document_parser.DocumentRejected, match="invalid_faq_schema"):
        document_parser.parse_document(source)


def test_worker_cli_requires_approved_boundary_arguments(tmp_path: Path) -> None:
    source = tmp_path / "faq.csv"
    source.write_text("question,answer\n연차는?,규정 참고\n", encoding="utf-8")
    output = tmp_path / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hr_chatbot.adapters.document_parser",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--inbox" in completed.stderr
    assert "--sha256" in completed.stderr
    assert not output.exists()


def test_worker_cli_writes_exact_output_schema(tmp_path: Path) -> None:
    source = tmp_path / "faq.csv"
    source.write_text("question,answer\n연차는?,규정 참고\n", encoding="utf-8")
    output = tmp_path / "output" / "result.json"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hr_chatbot.adapters.document_parser",
            "--input",
            str(source),
            "--inbox",
            str(tmp_path),
            "--sha256",
            sha256(source.read_bytes()).hexdigest(),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload) == {"document", "blocks", "tables", "warnings"}
