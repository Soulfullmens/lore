"""EpisodicMemoryBackend — the memory-ON backend for Phase 1.

Reconciled against the real MemoryBackend protocol in protocols.py. This
implements the SAME interface as NullMemoryBackend (setup, close, retrieve,
record_episode, reflect, consolidate, forget, stats) so the harness runs
byte-identical code paths. The ONLY difference is retrieve() returns real
past episodes instead of [].

Phase 1 is episodic + naive retrieval: no consolidation into Lessons yet
(Phase 2), no confidence weighting yet (Phase 3). Retrieval score is pure
similarity; the relevance x confidence x recency blend arrives in Phase 5.
"""
from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from ..models import (
    CreditUpdate,
    Episode,
    MemoryKind,
    OutcomeStatus,
    RetrievedMemory,
)
from .embedding import HashEmbedder
from .episode_store import SqliteEpisodeStore


@dataclass(slots=True)
class _EpisodicConsolidationReport:
    episodes_seen: int = 0
    lessons_created: int = 0
    lessons_merged: int = 0


@dataclass(slots=True)
class _EpisodicForgetReport:
    scanned: int = 0
    pruned: int = 0


class EpisodicMemoryBackend:
    """MemoryBackend backed by SqliteEpisodeStore + an EmbeddingProvider.

    Satisfies the exact same MemoryBackend protocol as NullMemoryBackend,
    so swapping it in changes nothing about the harness code path. Any
    measured lift is attributable to memory and nothing else.
    """

    def __init__(
        self,
        store: SqliteEpisodeStore | None = None,
        embedder: HashEmbedder | None = None,
        *,
        db_path: str = ":memory:",
        dim: int = 256,
        retrieve_outcomes: Sequence[OutcomeStatus] = (OutcomeStatus.SUCCESS,),
    ) -> None:
        self._embedder = embedder or HashEmbedder(dim=dim)
        self._store = store or SqliteEpisodeStore(db_path, dim=self._embedder.dim)
        if self._store.dim != self._embedder.dim:
            raise ValueError(
                f"store dim {self._store.dim} != embedder dim {self._embedder.dim}"
            )
        self._retrieve_outcomes = retrieve_outcomes

    # ---- MemoryBackend protocol ------------------------------------------ #

    def setup(self) -> None:
        pass  # SQLite connection is created in __init__

    def close(self) -> None:
        self._store.close()

    def retrieve(
        self,
        query: str,
        *,
        k: int = 5,
        exclude_ids: Collection[str] = (),
    ) -> list[RetrievedMemory]:
        """Retrieve the k nearest successful episodes to the query text.

        exclude_ids is the ablation seam — leave-one-out passes the target
        episode id here to measure its causal contribution.
        """
        if k <= 0 or self._store.count() == 0:
            return []
        vec = self._embedder.embed([query])[0]
        return self._store.search(
            vec, k, exclude_ids=exclude_ids, outcomes=self._retrieve_outcomes
        )

    def record_episode(self, episode: Episode) -> None:
        """Embed and persist an episode. Append-only, hot path, cheap."""
        text = episode.task_description or episode.task_id
        vec = self._embedder.embed([text])[0]
        self._store.add(episode, vec)

    def reflect(
        self,
        episode: Episode,
        retrieved: Sequence[RetrievedMemory],
    ) -> list[CreditUpdate]:
        """Phase 3 — no-op for now."""
        return []

    def consolidate(self) -> _EpisodicConsolidationReport:
        """Phase 2 — no-op for now."""
        return _EpisodicConsolidationReport()

    def forget(self) -> _EpisodicForgetReport:
        """Phase 4 — no-op for now."""
        return _EpisodicForgetReport()

    def stats(self) -> dict[str, int]:
        return {"episode": self._store.count(), "lesson": 0, "skill": 0}
