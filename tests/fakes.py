"""Reusable deterministic test adapters."""

from __future__ import annotations

from collections.abc import Sequence

from hr_chatbot.domain import (
    ChatTurn,
    DraftAnswer,
    RankedChunk,
    SearchFilters,
)


class InMemoryVectorStore:
    def __init__(self, chunks: Sequence[RankedChunk]) -> None:
        self._chunks = tuple(chunks)

    def search(
        self, query_vector: Sequence[float], filters: SearchFilters, k: int
    ) -> list[RankedChunk]:
        del query_vector
        expected_status = "approved" if filters.mode == "active" else "candidate"
        eligible = (
            chunk
            for chunk in self._chunks
            if chunk.index_id == filters.index_id
            and chunk.index_status == expected_status
            and chunk.access_level == filters.access_level
            and chunk.effective_from <= filters.effective_at
            and (chunk.expires_at is None or chunk.expires_at > filters.effective_at)
        )
        return sorted(eligible, key=lambda chunk: (-chunk.score, chunk.chunk_id))[:k]


class DeterministicGenerator:
    def __init__(self, outcome: DraftAnswer | Exception) -> None:
        self._outcome = outcome

    def generate(
        self,
        question: str,
        evidence: Sequence[RankedChunk],
        history: Sequence[ChatTurn],
    ) -> DraftAnswer:
        del question, evidence, history
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome
