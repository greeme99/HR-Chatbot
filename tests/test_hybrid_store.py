"""Tests for Hybrid Vector Store."""

from pathlib import Path
import pytest
from hr_chatbot.adapters.document_parser import DocumentParser
from hr_chatbot.adapters.hybrid_store import HybridVectorStore, LocalEmbedder

HR_RULES_DIR = Path("docs/HR-Rules")


def test_hybrid_store_indexing_and_search() -> None:
    csv_file = HR_RULES_DIR / "HR_Rules_and_FAQ_sample.csv"
    parser = DocumentParser()
    _, chunks = parser.parse_csv(csv_file)

    store = HybridVectorStore()
    store.add_chunks(chunks)

    # 1. Search for annual leave
    results = store.search("연차휴가 발생 기준과 이월 여부", top_k=3)
    assert len(results) > 0
    top_chunk = results[0].chunk
    assert "연차" in top_chunk.text or "휴가" in top_chunk.text

    # 2. Search for wedding condolence
    results2 = store.search("본인 결혼 시 축의금과 화환", top_k=3)
    assert len(results2) > 0
    assert any("500,000" in r.chunk.text or "결혼" in r.chunk.text for r in results2)

    # 3. Exact Article Search
    results3 = store.search("제10조 근무시간", top_k=3)
    assert len(results3) > 0
    assert any("근무시간" in r.chunk.text for r in results3)
