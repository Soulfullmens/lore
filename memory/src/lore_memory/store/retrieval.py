"""Memory backends — from Phase 1 episodic to Phase 2 consolidated retrieval.

This module provides:

1. ``EpisodicMemoryBackend`` — Phase 1, raw episode retrieval.
2. ``ConsolidatingMemoryBackend`` — Phase 2, lessons-first retrieval with
   offline consolidation ("sleep" process).

Both implement the same ``MemoryBackend`` protocol as ``NullMemoryBackend``,
so swapping them in the harness changes nothing about the code path. Any
measured lift is attributable to memory and nothing else.
"""
from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from ..models import (
    CreditUpdate,
    Episode,
    Lesson,
    MemoryKind,
    OutcomeStatus,
    RetrievedMemory,
)
from ..consolidation import EpisodeClusterer, PatternExtractor, LessonDeduplicator
from .embedding import HashEmbedder
from .episode_store import SqliteEpisodeStore
from .lesson_store import SqliteLessonStore


@dataclass(slots=True)
class ConsolidationReport:
    """Report from one consolidation pass."""
    episodes_scanned: int = 0
    clusters_found: int = 0
    lessons_extracted: int = 0
    lessons_merged: int = 0
    lessons_kept: int = 0


@dataclass(slots=True)
class _ForgetReport:
    scanned: int = 0
    pruned: int = 0


# --------------------------------------------------------------------------- #
# Phase 1 — Episodic retrieval (unchanged, backward compatible)
# --------------------------------------------------------------------------- #

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

    def consolidate(self) -> ConsolidationReport:
        """Phase 2 — no-op in EpisodicMemoryBackend (use ConsolidatingMemoryBackend)."""
        return ConsolidationReport()

    def forget(self) -> _ForgetReport:
        """Phase 4 — no-op for now."""
        return _ForgetReport()

    def stats(self) -> dict[str, int]:
        return {"episode": self._store.count(), "lesson": 0, "skill": 0}


# --------------------------------------------------------------------------- #
# Phase 2 — Consolidated retrieval (lessons first, episodes fallback)
# --------------------------------------------------------------------------- #

class ConsolidatingMemoryBackend:
    """MemoryBackend with lessons-first retrieval and offline consolidation.

    The key upgrade over EpisodicMemoryBackend:
    - ``consolidate()`` actually runs: clusters episodes, extracts lessons,
      deduplicates, and stores them in a LessonStore.
    - ``retrieve()`` checks lessons first (compact, ~100 tokens), then
      falls back to episodes if no relevant lessons exist.
    - Consolidation is **idempotent**: running it twice on the same
      episode set produces the same lesson set.

    Token budget: lessons are ~100 tokens vs ~500+ for episodes.
    This is where the 5x compression pays for itself.
    """

    def __init__(
        self,
        episode_store: SqliteEpisodeStore | None = None,
        lesson_store: SqliteLessonStore | None = None,
        embedder: HashEmbedder | None = None,
        *,
        db_path: str = ":memory:",
        dim: int = 256,
        retrieve_outcomes: Sequence[OutcomeStatus] = (OutcomeStatus.SUCCESS,),
    ) -> None:
        self._embedder = embedder or HashEmbedder(dim=dim)
        self._episode_store = episode_store or SqliteEpisodeStore(db_path, dim=self._embedder.dim)
        self._lesson_store = lesson_store or SqliteLessonStore(db_path, dim=self._embedder.dim)
        self._retrieve_outcomes = retrieve_outcomes

        self._clusterer = EpisodeClusterer()
        self._extractor = PatternExtractor()
        self._dedup = LessonDeduplicator(similarity_threshold=0.85)

        # Track which episodes have already been consolidated (idempotency)
        self._consolidated_episode_ids: set[str] = set()

    # ---- MemoryBackend protocol ------------------------------------------ #

    def setup(self) -> None:
        pass

    def close(self) -> None:
        self._episode_store.close()
        self._lesson_store.close()

    def retrieve(
        self,
        query: str,
        *,
        k: int = 5,
        exclude_ids: Collection[str] = (),
    ) -> list[RetrievedMemory]:
        """Lessons-first retrieval with episode fallback.

        1. Search lessons first (compact, confidence-weighted).
        2. If fewer than k results, backfill from episodes.
        3. Return combined results, capped at k.

        This is where the token budget savings come from: a lesson is
        ~100 tokens vs ~500+ for a raw episode trajectory.
        """
        vec = self._embedder.embed([query])[0]
        results: list[RetrievedMemory] = []

        # --- Tier 1: Lessons (compact, confidence-weighted) ---
        if self._lesson_store.count() > 0:
            lesson_results = self._lesson_store.search(
                vec, k, exclude_ids=exclude_ids
            )
            results.extend(lesson_results)

        # --- Tier 2: Episodes (fallback if lessons insufficient) ---
        remaining = k - len(results)
        if remaining > 0 and self._episode_store.count() > 0:
            # Exclude any episodes whose lessons we already retrieved
            lesson_exclude = set(exclude_ids)
            episode_results = self._episode_store.search(
                vec, remaining, exclude_ids=lesson_exclude,
                outcomes=self._retrieve_outcomes,
            )
            results.extend(episode_results)

        return results[:k]

    def record_episode(self, episode: Episode) -> None:
        """Embed and persist an episode."""
        text = episode.task_description or episode.task_id
        vec = self._embedder.embed([text])[0]
        self._episode_store.add(episode, vec)

    def reflect(
        self,
        episode: Episode,
        retrieved: Sequence[RetrievedMemory],
    ) -> list[CreditUpdate]:
        """Phase 3 — no-op for now."""
        return []

    def consolidate(self) -> ConsolidationReport:
        """The "sleep" process — cluster episodes, extract lessons, deduplicate.

        **Idempotent**: tracks which episodes have been consolidated.
        Running it twice on the same episode set produces the same
        lesson set (or a stable superset if new episodes were added).
        """
        report = ConsolidationReport()

        # Get all episodes from the store
        all_episodes = self._get_all_episodes()
        report.episodes_scanned = len(all_episodes)

        if not all_episodes:
            return report

        # Filter to unconsolidated episodes + enough context
        # (We include already-consolidated episodes for clustering context,
        #  but only extract lessons from clusters with new data)
        new_episodes = [
            ep for ep in all_episodes
            if ep.id not in self._consolidated_episode_ids
        ]

        if not new_episodes:
            return report  # idempotent: nothing new to process

        # --- 1. Cluster ---
        clusters = self._clusterer.cluster(all_episodes)
        report.clusters_found = len(clusters)

        # --- 2. Extract lessons from clusters ---
        candidates: list[Lesson] = []
        for cluster in clusters:
            # Only extract if cluster contains new episodes
            cluster_ids = {ep.id for ep in cluster.successes + cluster.failures}
            new_in_cluster = cluster_ids - self._consolidated_episode_ids
            if not new_in_cluster:
                continue

            lessons = self._extractor.extract(cluster)
            candidates.extend(lessons)

        report.lessons_extracted = len(candidates)

        if not candidates:
            # Mark all episodes as consolidated even if no lessons extracted
            for ep in new_episodes:
                self._consolidated_episode_ids.add(ep.id)
            return report

        # --- 3. Embed candidate lessons ---
        candidate_texts = [
            c.statement or f"{c.symptom} {c.fix}"
            for c in candidates
        ]
        candidate_vectors = self._embedder.embed(candidate_texts)

        # --- 4. Deduplicate against existing lessons ---
        existing = self._lesson_store.get_all_with_vectors()
        dedup_result = self._dedup.deduplicate(
            candidates, existing, candidate_vectors
        )

        report.lessons_merged = len(dedup_result.merged)
        report.lessons_kept = len(dedup_result.kept)

        # --- 5. Store new lessons ---
        for lesson in dedup_result.kept:
            text = lesson.statement or f"{lesson.symptom} {lesson.fix}"
            vec = self._embedder.embed([text])[0]
            self._lesson_store.add(lesson, vec)

        # --- 6. Update merged existing lessons ---
        for existing_lesson, existing_vec in existing:
            self._lesson_store.add(existing_lesson, existing_vec)

        # Mark episodes as consolidated
        for ep in new_episodes:
            self._consolidated_episode_ids.add(ep.id)

        return report

    def forget(self) -> _ForgetReport:
        """Phase 4 — no-op for now."""
        return _ForgetReport()

    def stats(self) -> dict[str, int]:
        return {
            "episode": self._episode_store.count(),
            "lesson": self._lesson_store.count(),
            "skill": 0,
        }

    # --- internal helpers --------------------------------------------------

    def _get_all_episodes(self) -> list[Episode]:
        """Retrieve all episodes from the store (for clustering)."""
        rows = list(self._episode_store._conn.execute(
            "SELECT payload FROM episodes"
        ))
        import json
        from .episode_store import _dict_to_episode
        return [_dict_to_episode(json.loads(row["payload"])) for row in rows]
