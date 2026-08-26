"""Domain models and value objects for HR Chatbot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Sequence


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    document_id: str
    version_id: str
    title: str
    document_kind: Literal["rule", "notice", "faq"]
    source_uri: str
    priority: int = 100
    effective_from: str = "2026-01-01"
    effective_to: str | None = None
    access_level: Literal["employee", "hr_only"] = "employee"
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    page_or_section: str
    text: str
    search_text: str
    document_kind: Literal["rule", "notice", "faq"] = "rule"
    priority: int = 100
    source_uri: str = ""
    effective_from: str = "2026-01-01"
    effective_to: str | None = None
    access_level: Literal["employee", "hr_only"] = "employee"
    table_id: str | None = None
    vector: Sequence[float] | None = None


@dataclass(frozen=True, slots=True)
class SearchFilters:
    effective_at: datetime | None = None
    access_level: Literal["employee", "hr_only"] = "employee"
    document_kind: Literal["rule", "notice", "faq"] | None = None
    document_id: str | None = None


@dataclass(frozen=True, slots=True)
class RankedChunk:
    chunk: KnowledgeChunk
    score: float
    match_type: Literal["hybrid", "dense", "lexical"] = "hybrid"


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    document_id: str
    title: str
    page_or_section: str
    source_uri: str
    snippet: str


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str
    timestamp: str = ""


@dataclass(frozen=True, slots=True)
class AnswerRequest:
    request_id: str
    question: str
    history: Sequence[ChatTurn] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AnswerResult:
    request_id: str
    question: str
    status: Literal["answered", "refused", "error"]
    answer_text: str
    citations: Sequence[Citation] = field(default_factory=tuple)
    retrieved_chunks: Sequence[RankedChunk] = field(default_factory=tuple)
    latency_ms: float = 0.0
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_type: Literal["answerable", "refusal"]
    target_doc: str
    target_section: str
    reference_answer: str
    category: str


@dataclass(frozen=True, slots=True)
class EvaluationResultItem:
    case_id: str
    question: str
    expected_type: Literal["answerable", "refusal"]
    actual_status: Literal["answered", "refused", "error"]
    hit_top5: bool
    is_correct: bool
    is_safe_refusal: bool
    latency_ms: float
    citations: Sequence[str] = field(default_factory=tuple)
    actual_answer: str = ""


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    evaluation_id: str
    timestamp: str
    total_count: int
    answerable_count: int
    refusal_count: int
    retrieval_hit_rate: float
    answer_accuracy: float
    refusal_accuracy: float
    critical_errors: int
    median_latency_ms: float
    items: Sequence[EvaluationResultItem] = field(default_factory=tuple)
