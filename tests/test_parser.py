"""Tests for Document Parser."""

from pathlib import Path
import pytest
from hr_chatbot.adapters.document_parser import DocumentParser

HR_RULES_DIR = Path("docs/HR-Rules")


def test_parse_csv_faq() -> None:
    csv_file = HR_RULES_DIR / "HR_Rules_and_FAQ_sample.csv"
    assert csv_file.exists(), f"File {csv_file} must exist"

    parser = DocumentParser()
    doc_ver, chunks = parser.parse_csv(csv_file)

    assert doc_ver.document_kind == "faq"
    assert len(chunks) >= 15
    # Verify article and question chunks exist
    leave_chunks = [c for c in chunks if "연차" in c.search_text or "경조" in c.search_text]
    assert len(leave_chunks) > 0
    assert all(c.chunk_id for c in chunks)


def test_parse_pdf_rules() -> None:
    pdf_file = HR_RULES_DIR / "MK I&C (주)_종합 인사규정집.pdf"
    if not pdf_file.exists():
        pytest.skip(f"{pdf_file} not found")

    parser = DocumentParser()
    doc_ver, chunks = parser.parse_pdf(pdf_file)

    assert doc_ver.document_kind == "rule"
    assert len(chunks) > 5
    assert any("근무시간" in c.text or "제10조" in c.text or "제25조" in c.text for c in chunks)


def test_parse_docx_rules() -> None:
    docx_file = HR_RULES_DIR / "MK I&C (주)_종합 인사규정집.docx"
    if not docx_file.exists():
        pytest.skip(f"{docx_file} not found")

    parser = DocumentParser()
    doc_ver, chunks = parser.parse_docx(docx_file)

    assert doc_ver.document_kind == "rule"
    assert len(chunks) > 5
