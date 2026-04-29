"""Sparkbot-level retrieval interfaces for Guardian memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .memory_os.api import MemoryGuardian
from .memory_os.schemas import Event


@dataclass(frozen=True)
class RetrievalHit:
    event: Event
    score: float
    mode: str


class Retriever(Protocol):
    mode: str

    def retrieve_scored(
        self,
        query: str,
        *,
        limit: int,
        session_id: str | None = None,
    ) -> list[RetrievalHit]:
        ...


class BM25Retriever:
    """Small shim over the vendored SQLite FTS5/BM25 retriever."""

    mode = "fts"

    def __init__(self, guardian: MemoryGuardian) -> None:
        self._guardian = guardian

    def retrieve_scored(
        self,
        query: str,
        *,
        limit: int,
        session_id: str | None = None,
    ) -> list[RetrievalHit]:
        return [
            RetrievalHit(event=event, score=float(score), mode=self.mode)
            for event, score in self._guardian.retriever.retrieve_scored(
                query,
                limit=limit,
                session_id=session_id,
                mode="fts",
            )
        ]


class HybridRetriever:
    """Optional hybrid retrieval using BM25 candidates plus embedding rerank."""

    mode = "hybrid"

    def __init__(self, guardian: MemoryGuardian) -> None:
        self._guardian = guardian

    def retrieve_scored(
        self,
        query: str,
        *,
        limit: int,
        session_id: str | None = None,
    ) -> list[RetrievalHit]:
        return [
            RetrievalHit(event=event, score=float(score), mode=self.mode)
            for event, score in self._guardian.retriever.retrieve_scored(
                query,
                limit=limit,
                session_id=session_id,
                mode="hybrid",
            )
        ]


def build_retriever(
    guardian: MemoryGuardian,
    *,
    requested_mode: str,
    embeddings_enabled: bool,
) -> Retriever:
    mode = (requested_mode or "fts").strip().lower()
    if embeddings_enabled and mode == "hybrid":
        return HybridRetriever(guardian)
    return BM25Retriever(guardian)
