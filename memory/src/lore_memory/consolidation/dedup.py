"""Lesson deduplication — prevents the commons from accumulating redundant knowledge.

When two lessons are similar:
1. Keep the one with higher confidence.
2. If confidence is comparable, keep the one with broader task_family
   coverage (more general > more specific).
3. Link the specific one as provenance of the general one.

This ensures the lesson store stays compact and preferentially retains
transferable, battle-tested knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Lesson, Vector


def _cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    return max(-1.0, min(1.0, dot))


@dataclass(slots=True)
class DeduplicationResult:
    """Result of deduplicating a batch of candidate lessons."""

    kept: list[Lesson] = field(default_factory=list)
    merged: list[tuple[str, str]] = field(default_factory=list)  # (absorbed_id, into_id)
    dropped: list[str] = field(default_factory=list)


class LessonDeduplicator:
    """Deduplicates candidate lessons against existing lessons and each other.

    Usage::

        dedup = LessonDeduplicator(similarity_threshold=0.85)
        result = dedup.deduplicate(candidates, existing, embedder)
    """

    def __init__(self, similarity_threshold: float = 0.85) -> None:
        self.threshold = similarity_threshold

    def deduplicate(
        self,
        candidates: list[Lesson],
        existing: list[tuple[Lesson, Vector]],
        candidate_vectors: list[Vector],
    ) -> DeduplicationResult:
        """Deduplicate candidates against existing lessons and each other.

        Args:
            candidates: New candidate lessons to add.
            existing: Currently stored lessons with their vectors.
            candidate_vectors: Embedding vectors for each candidate
                (same order as candidates).

        Returns:
            DeduplicationResult with kept, merged, and dropped lesson ids.
        """
        result = DeduplicationResult()

        for i, (candidate, c_vec) in enumerate(zip(candidates, candidate_vectors)):
            # Check against existing lessons
            merged_into = self._check_existing(candidate, c_vec, existing)
            if merged_into is not None:
                result.merged.append((candidate.id, merged_into.id))
                # Update the existing lesson's provenance
                merged_into.source_episode_ids = list(set(
                    merged_into.source_episode_ids + candidate.source_episode_ids
                ))
                continue

            # Check against already-kept candidates
            merged_into_kept = self._check_kept(
                candidate, c_vec, result.kept,
                [candidate_vectors[j] for j in range(len(result.kept))],
            )
            if merged_into_kept is not None:
                result.merged.append((candidate.id, merged_into_kept.id))
                merged_into_kept.source_episode_ids = list(set(
                    merged_into_kept.source_episode_ids + candidate.source_episode_ids
                ))
                continue

            result.kept.append(candidate)

        return result

    def _check_existing(
        self,
        candidate: Lesson,
        c_vec: Vector,
        existing: list[tuple[Lesson, Vector]],
    ) -> Lesson | None:
        """Check if candidate duplicates an existing lesson.

        Returns the existing lesson to merge into, or None if novel.
        """
        for ex_lesson, ex_vec in existing:
            sim = _cosine(c_vec, ex_vec)
            if sim >= self.threshold:
                # Similar enough to be a duplicate — keep the better one
                winner = self._pick_winner(candidate, ex_lesson)
                if winner is ex_lesson:
                    return ex_lesson  # absorb candidate into existing
                # candidate is better: update existing in-place
                ex_lesson.symptom = candidate.symptom
                ex_lesson.fix = candidate.fix
                ex_lesson.rationale = candidate.rationale
                ex_lesson.statement = candidate.statement
                return ex_lesson

        return None

    def _check_kept(
        self,
        candidate: Lesson,
        c_vec: Vector,
        kept: list[Lesson],
        kept_vectors: list[Vector],
    ) -> Lesson | None:
        """Check if candidate duplicates a lesson we're already keeping."""
        for k_lesson, k_vec in zip(kept, kept_vectors):
            sim = _cosine(c_vec, k_vec)
            if sim >= self.threshold:
                winner = self._pick_winner(candidate, k_lesson)
                if winner is k_lesson:
                    return k_lesson
                # candidate is better: update kept in-place
                k_lesson.symptom = candidate.symptom
                k_lesson.fix = candidate.fix
                k_lesson.rationale = candidate.rationale
                k_lesson.statement = candidate.statement
                return k_lesson

        return None

    def _pick_winner(self, a: Lesson, b: Lesson) -> Lesson:
        """Pick the better lesson between two similar ones.

        Preference order:
        1. Higher confidence (battle-tested)
        2. Broader scope (task_family > task_id specific)
        3. More source episodes (more evidence)
        """
        # Confidence difference
        conf_diff = a.bayesian_confidence() - b.bayesian_confidence()
        if abs(conf_diff) > 0.1:
            return a if conf_diff > 0 else b

        # Scope breadth: family-scoped > task-scoped
        a_broad = bool(a.task_family and not a.task_id)
        b_broad = bool(b.task_family and not b.task_id)
        if a_broad and not b_broad:
            return a
        if b_broad and not a_broad:
            return b

        # More provenance
        if len(a.source_episode_ids) > len(b.source_episode_ids):
            return a
        if len(b.source_episode_ids) > len(a.source_episode_ids):
            return b

        # Tiebreak: keep the newer one (more recent data)
        return a if a.created_at >= b.created_at else b
