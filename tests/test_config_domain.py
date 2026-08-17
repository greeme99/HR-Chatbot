from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hr_chatbot import config, domain
from tests import fakes

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_app_config_loads_security_limits() -> None:
    loaded = config.AppConfig.load(PROJECT_ROOT / "config" / "app.toml")

    assert loaded.token_profile.model_n_ctx == 4096
    assert loaded.parser_limits.max_file_mib == 50
    assert loaded.parser_limits.max_pdf_pages == 500
    assert loaded.top_k == 5
    assert loaded.allowed_source_hosts == ()


def test_app_config_rejects_non_positive_top_k() -> None:
    loaded = config.AppConfig.load(PROJECT_ROOT / "config" / "app.toml")

    with pytest.raises(ValueError, match="invalid_config:top_k"):
        config.AppConfig(loaded.token_profile, loaded.parser_limits, 0, ())


def test_app_config_rejects_url_in_allowed_hosts() -> None:
    loaded = config.AppConfig.load(PROJECT_ROOT / "config" / "app.toml")

    with pytest.raises(ValueError, match="invalid_config:allowed_hosts"):
        config.AppConfig(
            loaded.token_profile,
            loaded.parser_limits,
            5,
            ("https://intranet.example.com/path",),
        )


def test_answer_request_rejects_over_2000_characters() -> None:
    with pytest.raises(ValueError, match="question_too_long"):
        domain.AnswerRequest(request_id="r1", question="가" * 2001, history=())


def test_answer_request_rejects_more_than_five_history_turns() -> None:
    turns = tuple(domain.ChatTurn(role="user", content=str(index)) for index in range(6))

    with pytest.raises(ValueError, match="history_too_long"):
        domain.AnswerRequest(request_id="r1", question="휴가 규정은?", history=turns)


def test_answer_status_is_closed_enum() -> None:
    with pytest.raises(ValueError, match="invalid_answer_status"):
        domain.AnswerResult(status="invented", answer_text="")


def test_answer_error_code_is_closed_enum() -> None:
    with pytest.raises(ValueError, match="invalid_error_code"):
        domain.AnswerResult(status="error", answer_text="", error_code="invented")


def test_token_profile_must_fit_model_context() -> None:
    with pytest.raises(ValueError, match="token_budget"):
        domain.TokenProfile(
            model_n_ctx=2048,
            max_input_tokens=3584,
            max_history_tokens=512,
            max_evidence_tokens=2304,
            max_output_tokens=512,
        )


def test_token_profile_partitions_input_budget() -> None:
    with pytest.raises(ValueError, match="token_budget"):
        domain.TokenProfile(
            model_n_ctx=4096,
            max_input_tokens=3584,
            max_history_tokens=1024,
            max_evidence_tokens=3000,
            max_output_tokens=512,
        )


def test_evaluation_search_requires_bound_scope() -> None:
    with pytest.raises(ValueError, match="evaluation_scope_required"):
        domain.SearchFilters(
            index_id="candidate-1",
            effective_at=datetime.now(UTC),
            mode="evaluation",
        )


def test_search_filters_reject_unknown_mode() -> None:
    with pytest.raises(ValueError, match="invalid_search_mode"):
        domain.SearchFilters(
            index_id="candidate-1",
            effective_at=datetime.now(UTC),
            mode="typo",
            candidate_manifest_hash="a" * 64,
            dataset_checksum="b" * 64,
        )


def test_in_memory_store_sorts_equal_scores_by_chunk_id() -> None:
    now = datetime.now(UTC)
    chunks = [
        domain.RankedChunk(
            "b", "v1", "B", 0.9, 300, now, "rule", "leave", index_id="approved-1"
        ),
        domain.RankedChunk(
            "a", "v1", "A", 0.9, 300, now, "rule", "leave", index_id="approved-1"
        ),
    ]
    store = fakes.InMemoryVectorStore(chunks)

    ranked = store.search(
        [1.0], domain.SearchFilters(index_id="approved-1", effective_at=now), k=2
    )

    assert [chunk.chunk_id for chunk in ranked] == ["a", "b"]


def test_in_memory_store_excludes_wrong_index_candidate_and_expired_chunks() -> None:
    now = datetime.now(UTC)
    chunks = [
        domain.RankedChunk(
            "valid",
            "v1",
            "valid",
            0.8,
            300,
            now - timedelta(days=1),
            "rule",
            "leave",
            index_id="approved-1",
        ),
        domain.RankedChunk(
            "candidate",
            "v1",
            "candidate",
            1.0,
            300,
            now - timedelta(days=1),
            "rule",
            "leave",
            index_id="approved-1",
            index_status="candidate",
        ),
        domain.RankedChunk(
            "expired",
            "v1",
            "expired",
            0.9,
            300,
            now - timedelta(days=2),
            "rule",
            "leave",
            index_id="approved-1",
            expires_at=now - timedelta(days=1),
        ),
        domain.RankedChunk(
            "wrong-index",
            "v1",
            "wrong",
            0.95,
            300,
            now - timedelta(days=1),
            "rule",
            "leave",
            index_id="approved-2",
        ),
    ]
    store = fakes.InMemoryVectorStore(chunks)

    ranked = store.search(
        [1.0], domain.SearchFilters(index_id="approved-1", effective_at=now), k=5
    )

    assert [chunk.chunk_id for chunk in ranked] == ["valid"]


def test_document_version_uses_kind_default_priority() -> None:
    version = domain.DocumentVersion(
        document_id="leave-policy",
        version_id="v1",
        title="휴가 규정",
        source_uri=None,
        content_hash="a" * 64,
        document_kind="rule",
        policy_subject="leave",
        effective_from=datetime.now(UTC),
    )

    assert version.priority == 300


def test_document_version_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="invalid_document_kind"):
        domain.DocumentVersion(
            document_id="leave-policy",
            version_id="v1",
            title="휴가 규정",
            source_uri=None,
            content_hash="a" * 64,
            document_kind="memo",
            policy_subject="leave",
            effective_from=datetime.now(UTC),
        )


def test_deterministic_generator_returns_configured_draft() -> None:
    draft = domain.DraftAnswer("연차는 규정에 따릅니다.", ("a",), domain.GenerationTiming())
    generator = fakes.DeterministicGenerator(draft)

    assert generator.generate("연차는?", (), ()) == draft
