"""Hybrid Vector Store combining Dense Embeddings with Lexical BM25 Search."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from hr_chatbot.domain import KnowledgeChunk, RankedChunk, SearchFilters


def tokenize_korean(text: str) -> list[str]:
    """Tokenize Korean text into words, compound subwords, article numbers and alphanumeric tokens."""
    cleaned = re.sub(r"[^\w\s가-힣0-9]", " ", text.lower())
    tokens = cleaned.split()

    # Extract 2-char subwords from Korean compound words
    subwords: list[str] = []
    for t in tokens:
        if len(t) >= 4 and re.match(r"^[가-힣]+$", t):
            for i in range(len(t) - 1):
                subwords.append(t[i : i + 2])

    # Extract article matches like '제10조', '제25조' or numbers with units
    articles = re.findall(r"제\s*\d+\s*조", text)
    clean_articles = [re.sub(r"\s+", "", a) for a in articles]

    return tokens + subwords + clean_articles


class LocalEmbedder:
    """Fast, deterministic semantic embedder combining Korean morphemes and subword n-grams."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name
        self._model = None
        self._is_transformer = False

        # Attempt to load local transformer ONLY if explicitly configured and available offline
        if model_name:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(model_name, local_files_only=True)
                self._is_transformer = True
            except Exception:
                self._model = None
                self._is_transformer = False

    def embed_texts(self, texts: Sequence[str]) -> np.ndarray:
        if self._is_transformer and self._model is not None:
            try:
                embeddings = self._model.encode(
                    list(texts),
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                return np.asarray(embeddings, dtype=np.float32)
            except Exception:
                pass

        # High-performance 512-dim Subword + N-gram Semantic Vectorizer
        dim = 512
        vectors = np.zeros((len(texts), dim), dtype=np.float32)

        for i, text in enumerate(texts):
            tokens = tokenize_korean(text)
            for token in tokens:
                # Word token feature
                h_token = abs(hash(token)) % dim
                vectors[i, h_token] += 1.5

                # Character sub-ngrams (2-gram, 3-gram)
                for n in (2, 3):
                    for j in range(len(token) - n + 1):
                        ngram = token[j : j + n]
                        h_ng = abs(hash(ngram)) % dim
                        vectors[i, h_ng] += 0.8

            norm = np.linalg.norm(vectors[i])
            if norm > 1e-6:
                vectors[i] /= norm
            else:
                vectors[i, 0] = 1.0

        return vectors

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])[0]


class BM25Index:
    """Pure-Python fast BM25 lexical search index."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0.0
        self.doc_freqs: list[Counter[str]] = []
        self.idf: dict[str, float] = {}
        self.doc_lens: list[int] = []

    def fit(self, documents: Sequence[str]) -> None:
        self.corpus_size = len(documents)
        self.doc_freqs = []
        self.doc_lens = []
        df: Counter[str] = Counter()

        for doc in documents:
            tokens = tokenize_korean(doc)
            self.doc_lens.append(len(tokens))
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            for token in freq:
                df[token] += 1

        self.avgdl = sum(self.doc_lens) / max(self.corpus_size, 1)

        self.idf = {}
        for word, count in df.items():
            self.idf[word] = math.log((self.corpus_size - count + 0.5) / (count + 0.5) + 1.0)

    def get_scores(self, query: str) -> np.ndarray:
        query_tokens = tokenize_korean(query)
        scores = np.zeros(self.corpus_size, dtype=np.float32)
        if self.corpus_size == 0 or not query_tokens:
            return scores

        for token in query_tokens:
            if token not in self.idf:
                continue
            idf_val = self.idf[token]
            for i, freq in enumerate(self.doc_freqs):
                if token in freq:
                    tf = freq[token]
                    doc_len = self.doc_lens[i]
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / max(self.avgdl, 1e-5)))
                    scores[i] += idf_val * (numerator / denominator)

        max_score = np.max(scores) if np.max(scores) > 0 else 1.0
        return scores / max_score


class HybridVectorStore:
    """Hybrid Vector Store combining Dense Vector similarity with BM25 Lexical Ranking."""

    def __init__(self, embedder: LocalEmbedder | None = None) -> None:
        self.embedder = embedder or LocalEmbedder()
        self.chunks: list[KnowledgeChunk] = []
        self.embeddings: np.ndarray | None = None
        self.bm25 = BM25Index()

    def add_chunks(self, chunks: Sequence[KnowledgeChunk]) -> None:
        if not chunks:
            return

        start_idx = len(self.chunks)
        self.chunks.extend(chunks)

        texts_to_embed = [c.search_text for c in chunks]
        new_vecs = self.embedder.embed_texts(texts_to_embed)

        if self.embeddings is None or self.embeddings.size == 0:
            self.embeddings = new_vecs
        else:
            self.embeddings = np.vstack([self.embeddings, new_vecs])

        # Re-index BM25 with all chunks
        all_texts = [c.search_text for c in self.chunks]
        self.bm25.fit(all_texts)

    def clear(self) -> None:
        self.chunks = []
        self.embeddings = None
        self.bm25 = BM25Index()

    def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        top_k: int = 5,
        dense_weight: float = 0.55,
        lexical_weight: float = 0.45,
    ) -> list[RankedChunk]:
        if not self.chunks or self.embeddings is None or len(self.chunks) == 0:
            return []

        # 1. Dense Cosine Similarity
        query_vec = self.embedder.embed_query(query)
        # Cosine similarity since embeddings are normalized
        dense_scores = np.dot(self.embeddings, query_vec)
        # Clip to [0, 1] range for score stability
        dense_scores = np.clip(dense_scores, 0.0, 1.0)

        # 2. BM25 Lexical Scores
        lexical_scores = self.bm25.get_scores(query)

        # 3. Exact Article & Keyword Boost
        article_matches = re.findall(r"제\s*\d+\s*조", query)
        clean_query_articles = [re.sub(r"\s+", "", a) for a in article_matches]

        ranked: list[RankedChunk] = []
        for idx, chunk in enumerate(self.chunks):
            # Apply filters
            if filters:
                if filters.document_kind and chunk.document_kind != filters.document_kind:
                    continue
                if filters.access_level and chunk.access_level != filters.access_level:
                    continue
                if filters.document_id and chunk.document_id != filters.document_id:
                    continue

            d_score = float(dense_scores[idx])
            l_score = float(lexical_scores[idx])

            # Article Boost
            art_boost = 0.0
            if clean_query_articles:
                for art in clean_query_articles:
                    if art in chunk.page_or_section or art in chunk.text:
                        art_boost += 0.25

            # Priority Weight (규정 300 > 공지 200 > FAQ 100)
            priority_factor = (chunk.priority / 1000.0) * 0.05

            combined_score = (dense_weight * d_score) + (lexical_weight * l_score) + art_boost + priority_factor

            ranked.append(
                RankedChunk(
                    chunk=chunk,
                    score=min(combined_score, 1.0),
                    match_type="hybrid" if l_score > 0.1 else "dense",
                )
            )

        # Sort by score descending, tie-break by chunk_id
        ranked.sort(key=lambda r: (-r.score, r.chunk.chunk_id))
        return ranked[:top_k]
