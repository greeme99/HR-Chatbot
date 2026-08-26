"""Tests for AnsweringEngine with Grounded Citations and Safe Refusals."""

from pathlib import Path
import pytest
from hr_chatbot.adapters.document_parser import DocumentParser
from hr_chatbot.adapters.hybrid_store import HybridVectorStore
from hr_chatbot.answering import AnsweringEngine
from hr_chatbot.domain import AnswerRequest

HR_RULES_DIR = Path("docs/HR-Rules")


@pytest.fixture
def populated_engine() -> AnsweringEngine:
    parser = DocumentParser()
    store = HybridVectorStore()

    for p in HR_RULES_DIR.glob("*.*"):
        if p.suffix.lower() in (".pdf", ".docx", ".csv"):
            try:
                _, chunks = parser.parse_file(p)
                store.add_chunks(chunks)
            except Exception:
                pass

    return AnsweringEngine(store)


def test_answer_valid_policy_question(populated_engine: AnsweringEngine) -> None:
    req = AnswerRequest(request_id="t1", question="1년 동안 80% 이상 출근하면 연차가 며칠 나오나요?")
    res = populated_engine.answer(req)

    assert res.status == "answered"
    assert len(res.citations) > 0
    assert "15일" in res.answer_text or "연차" in res.answer_text
    assert res.latency_ms > 0


def test_safe_refusal_personal_data(populated_engine: AnsweringEngine) -> None:
    req = AnswerRequest(request_id="t2", question="내 남은 잔여 연차 일수 며칠인지 알려줘")
    res = populated_engine.answer(req)

    assert res.status == "refused"
    assert "개인정보" in res.answer_text or "My HR" in res.answer_text


def test_safe_refusal_out_of_domain(populated_engine: AnsweringEngine) -> None:
    req = AnswerRequest(request_id="t3", question="오늘 서울 날씨 어때?")
    res = populated_engine.answer(req)

    assert res.status == "refused"
    assert "인사" in res.answer_text
