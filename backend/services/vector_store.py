"""Lightweight in-memory vector store for RAG over analytics context.

Uses TF-IDF vectorization with numpy cosine similarity — no external vector
database required. Chunks of analytics data and company context are indexed
at request time and queried by the opportunity agent nodes.

This is intentionally minimal: the store lives for the lifetime of one
opportunity discovery request and is not persisted across requests.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np


class SimpleVectorStore:
    """In-memory TF-IDF vector store for single-request RAG.

    Designed to hold ~20–100 short text chunks and answer a handful of
    queries per agent run. Scales to thousands of chunks if needed — the
    bottleneck is vocab construction, which is O(n * avg_tokens).
    """

    def __init__(self) -> None:
        self._documents: list[str] = []
        self._metadata: list[dict[str, Any]] = []
        self._vocab: dict[str, int] = {}
        self._matrix: np.ndarray | None = None  # shape (n_docs, vocab_size)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b[a-z0-9]+\b", text.lower())

    def _build_vocab(self) -> None:
        all_tokens: set[str] = set()
        for doc in self._documents:
            all_tokens.update(self._tokenize(doc))
        self._vocab = {token: i for i, token in enumerate(sorted(all_tokens))}

    def _vectorize(self, text: str) -> np.ndarray:
        tokens = self._tokenize(text)
        vec = np.zeros(len(self._vocab), dtype=np.float32)
        for token in tokens:
            if token in self._vocab:
                vec[self._vocab[token]] += 1.0
        total = vec.sum()
        if total > 0:
            vec /= total
        return vec

    def add_documents(
        self,
        documents: list[str],
        metadata: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add documents and rebuild the TF-IDF matrix."""
        if not documents:
            return
        self._documents.extend(documents)
        if metadata:
            self._metadata.extend(metadata)
        else:
            self._metadata.extend([{} for _ in documents])
        self._build_vocab()
        self._matrix = np.stack([self._vectorize(doc) for doc in self._documents])

    def query(
        self,
        query: str,
        n_results: int = 5,
        min_score: float = 0.0,
    ) -> list[tuple[str, dict[str, Any], float]]:
        """Return top-n documents by cosine similarity to query.

        Returns list of (document_text, metadata, similarity_score).
        """
        if self._matrix is None or len(self._documents) == 0:
            return []

        query_vec = self._vectorize(query)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        doc_norms = np.linalg.norm(self._matrix, axis=1)
        denominators = doc_norms * query_norm
        denominators = np.where(denominators == 0, 1e-10, denominators)
        similarities = (self._matrix @ query_vec) / denominators

        top_indices = np.argsort(similarities)[::-1][:n_results]
        return [
            (self._documents[i], self._metadata[i], float(similarities[i]))
            for i in top_indices
            if float(similarities[i]) >= min_score
        ]

    def get_top_documents(self, n: int = 10) -> list[str]:
        """Return the first n documents without scoring (for full-context mode)."""
        return self._documents[:n]

    def clear(self) -> None:
        self._documents = []
        self._metadata = []
        self._vocab = {}
        self._matrix = None

    def __len__(self) -> int:
        return len(self._documents)
