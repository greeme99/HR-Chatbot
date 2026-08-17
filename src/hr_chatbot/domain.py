"""Domain contracts for the local HR RAG prototype."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

AnswerStatus = Literal["answered", "refused", "retrieval_only", "degraded", "error"]
ErrorCode = Literal[
    "invalid_input",
    "no_evidence",
    "storage_unavailable",
    "model_unavailable",
    "model_timeout",
    "validation_failed",
]
DocumentKind = Literal["rule", "notice", "faq"]
IndexStatus = Literal["candidate", "approved", "retired"]

ANSWER_STATUSES = frozenset({"answered", "refused", "retrieval_only", "degraded", "error"})
ERROR_CODES = frozenset(
    {
        "invalid_input",
        "no_evidence",
        "storage_unavailable",
        "model_unavailable",
        "model_timeout",
        "validation_failed",
    }
)


@dataclass(frozen=True, slots=True)
class TokenProfile:
    model_n_ctx: int
    max_input_tokens: int
    max_history_tokens: int
    max_evidence_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        values = (
            self.model_n_ctx,
            self.max_input_tokens,
            self.max_history_tokens,
            self.max_evidence_tokens,
            self.max_output_tokens,
        )
        if any(value <= 0 for value in values):
            raise ValueError("token_budget")
        if self.max_input_tokens + self.max_output_tokens > self.model_n_ctx:
            raise ValueError("token_budget")
        if self.max_history_tokens + self.max_evidence_tokens > self.max_input_tokens:
            raise ValueError("token_budget")


@dataclass(frozen=True, slots=True)
class ParserLimits:
    max_file_mib: int
    max_pdf_pages: int
    max_archive_mib: int
    max_archive_entries: int
    max_compression_ratio: int
    timeout_seconds: int
    max_rss_mib: int

    def __post_init__(self) -> None:
        values = (
            self.max_file_mib,
            self.max_pdf_pages,
            self.max_archive_mib,
            self.max_archive_entries,
            self.max_compression_ratio,
            self.timeout_seconds,
            self.max_rss_mib,
        )
        if any(value <= 0 for value in values):
            raise ValueError("parser_limit")


@dataclass(frozen=True, slots=True)
class BuildConfig:
    parser_version: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    embedding_model: str
    embedding_revision: str
    embedding_dimension: int
    normalize_embeddings: bool
    artifact_manifest_hash: str


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class AnswerRequest:
    request_id: str
    question: str
    history: tuple[ChatTurn, ...]
    index_id: str | None = None

    def __post_init__(self) -> None:
        if len(self.question) > 2_000:
            raise ValueError("question_too_long")
        if len(self.history) > 5:
            raise ValueError("history_too_long")


@dataclass(frozen=True, slots=True)
class SearchFilters:
    index_id: str
    effective_at: datetime
    access_level: Literal["employee"] = "employee"
    mode: Literal["active", "evaluation"] = "active"
    candidate_manifest_hash: str | None = None
    dataset_checksum: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"active", "evaluation"}:
            raise ValueError("invalid_search_mode")
        if self.mode == "evaluation" and not (
            self.candidate_manifest_hash and self.dataset_checksum
        ):
            raise ValueError("evaluation_scope_required")


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    document_id: str
    version_id: str
    title: str
    source_uri: str | None
    content_hash: str
    document_kind: DocumentKind
    policy_subject: str
    effective_from: datetime
    priority: int = 0
    expires_at: datetime | None = None
    access_level: Literal["employee"] = "employee"

    def __post_init__(self) -> None:
        default_priorities = {"rule": 300, "notice": 200, "faq": 100}
        if self.document_kind not in default_priorities:
            raise ValueError("invalid_document_kind")
        if self.priority == 0:
            object.__setattr__(self, "priority", default_priorities[self.document_kind])
        elif self.priority <= 0:
            raise ValueError("invalid_document_priority")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    version_id: str
    index_id: str
    text: str
    vector: tuple[float, ...]
    content_hash: str
    document_kind: DocumentKind
    policy_subject: str
    priority: int
    effective_from: datetime
    expires_at: datetime | None = None
    access_level: Literal["employee"] = "employee"
    page: int | None = None
    section: str | None = None
    table_markdown: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeIndex:
    index_id: str
    status: IndexStatus
    embedding_model: str
    embedding_revision: str
    config_hash: str
    manifest_hash: str
    created_at: datetime
    approved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BuildAttempt:
    attempt_id: str
    status: Literal["succeeded", "failed"]
    started_at: datetime
    finished_at: datetime
    index_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationScope:
    index_id: str
    candidate_manifest_hash: str
    dataset_checksum: str


@dataclass(frozen=True, slots=True)
class GenerationTiming:
    first_token_ms: float | None = None
    total_ms: float | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    chunk_id: str
    document_title: str
    location: str
    source_uri: str | None = None


@dataclass(frozen=True, slots=True)
class RankedChunk:
    chunk_id: str
    version_id: str
    text: str
    score: float
    priority: int
    effective_from: datetime
    document_kind: DocumentKind
    policy_subject: str
    title: str = ""
    location: str = ""
    source_uri: str | None = None
    index_id: str = ""
    index_status: IndexStatus = "approved"
    expires_at: datetime | None = None
    access_level: Literal["employee"] = "employee"


@dataclass(frozen=True, slots=True)
class DraftAnswer:
    answer_text: str
    citation_chunk_ids: tuple[str, ...]
    timing: GenerationTiming


@dataclass(frozen=True, slots=True)
class CandidateRef:
    index_id: str
    manifest_hash: str
    row_count: int


@dataclass(frozen=True, slots=True)
class IndexTransitionResult:
    status: Literal["applied", "conflict", "rejected"]
    active_index_id: str | None
    previous_index_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_type: Literal["answerable", "refusal"]
    document_version_id: str | None
    location: str | None
    anchor_text: str | None
    anchor_hash: str | None
    reference_answer: str | None
    critical_facts: tuple[str, ...]
    category: str


@dataclass(frozen=True, slots=True)
class DatasetApproval:
    dataset_checksum: str
    actor: str
    approved_at: datetime


@dataclass(frozen=True, slots=True)
class CandidateGateReport:
    report_id: str
    index_id: str
    candidate_manifest_hash: str
    dataset_checksum: str
    checks: tuple[tuple[str, bool], ...]
    passed: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    evaluation_id: str
    index_id: str
    dataset_checksum: str
    state: Literal["running", "awaiting_review", "finalized"]
    retrieval_hits: int
    refusal_hits: int
    case_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class HumanReview:
    evaluation_id: str
    case_id: str
    correctness: bool
    grounding: bool
    safety: bool
    comment: str
    actor: str
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class FinalizedEvaluationReport:
    evaluation_id: str
    index_id: str
    dataset_checksum: str
    candidate_manifest_hash: str
    retrieval_hits: int
    generation_hits: int
    refusal_hits: int
    critical_errors: int
    answerable_median_ms: float
    candidate_gate_hash: str
    finalized_at: datetime
    passed: bool


@dataclass(frozen=True, slots=True)
class Feedback:
    feedback_id: str
    question_snapshot: str
    answer_snapshot: str
    citation_ids: tuple[str, ...]
    helpful: bool
    comment: str
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RetentionReport:
    run_id: str
    deleted_records: int
    failed_paths: tuple[str, ...]
    sampled_recovery_passed: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReleaseGateReport:
    report_id: str
    candidate_gate_hash: str
    environment_checks: tuple[tuple[str, bool], ...]
    browser_checks: tuple[tuple[str, bool], ...]
    retention_checks: tuple[tuple[str, bool], ...]
    passed: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AnswerResult:
    status: AnswerStatus
    answer_text: str
    evidence: tuple[RankedChunk, ...] = ()
    citations: tuple[Citation, ...] = ()
    refusal_reason: str | None = None
    error_code: ErrorCode | None = None
    timings: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    model_id: str | None = None
    index_id: str | None = None
    config_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in ANSWER_STATUSES:
            raise ValueError("invalid_answer_status")
        if self.error_code is not None and self.error_code not in ERROR_CODES:
            raise ValueError("invalid_error_code")


class VectorStore(Protocol):
    def search(
        self, query_vector: Sequence[float], filters: SearchFilters, k: int
    ) -> list[RankedChunk]: ...


class Generator(Protocol):
    def generate(
        self,
        question: str,
        evidence: Sequence[RankedChunk],
        history: Sequence[ChatTurn],
    ) -> DraftAnswer: ...
