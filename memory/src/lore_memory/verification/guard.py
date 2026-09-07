"""NegativeGuardGenerator — emits guard lessons when positive advice harms.

When a lesson receives CAUSED_FAIL credit (baseline PASS → treatment FAIL),
the generator creates a negative lesson that explicitly blocks the harmful
lesson for the specific model. This prevents the Phase 1 scenario where
the asyncio.gather lesson broke 100% of treatment runs.

Guard retrieval flow:
    1. Search for positive lessons → candidates
    2. Check active guards for each candidate (by parent_lesson_id + model)
    3. Only inject candidates not blocked by a guard
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models import Lesson, LessonScope, LessonType, new_id
from ..store.lesson_store import SqliteLessonStore
from .reflector import CausalAttribution

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GuardReport:
    """Report from a guard generation attempt."""
    guard_emitted: bool
    guard_id: str = ""
    parent_lesson_id: str = ""
    model: str = ""
    reason: str = ""


class NegativeGuardGenerator:
    """Generates negative lesson guards when a lesson causes harm.

    Usage::

        gen = NegativeGuardGenerator(lesson_store, embedder)
        report = gen.maybe_emit(
            lesson_id="abc123",
            attribution=CausalAttribution.CAUSED_FAIL,
            model="openai/gpt-4o-mini",
            task_id="acme-stream-consumer",
        )
    """

    def __init__(
        self,
        lesson_store: SqliteLessonStore,
        embedder: object | None = None,
        *,
        harm_threshold: int = 1,
    ) -> None:
        self._store = lesson_store
        self._embedder = embedder
        self._harm_threshold = harm_threshold

    def maybe_emit(
        self,
        lesson_id: str,
        attribution: CausalAttribution,
        *,
        model: str = "",
        task_id: str = "",
    ) -> GuardReport:
        """Emit a negative guard if the lesson caused harm.

        Only triggers on CAUSED_FAIL attribution. If the parent lesson
        has already been guarded for this model, returns a no-op report.
        """
        if attribution != CausalAttribution.CAUSED_FAIL:
            return GuardReport(
                guard_emitted=False,
                parent_lesson_id=lesson_id,
                model=model,
                reason=f"Attribution is {attribution.value}, not CAUSED_FAIL",
            )

        parent = self._store.get(lesson_id)
        if parent is None:
            return GuardReport(
                guard_emitted=False,
                parent_lesson_id=lesson_id,
                model=model,
                reason="Parent lesson not found in store",
            )

        # Check if a guard already exists for this parent + model
        existing_guards = self._store.get_guards_for_parent(lesson_id)
        for g in existing_guards:
            if model in g.model_confidence:
                logger.debug(
                    "Guard already exists for lesson %s / model %s",
                    lesson_id, model,
                )
                return GuardReport(
                    guard_emitted=False,
                    guard_id=g.id,
                    parent_lesson_id=lesson_id,
                    model=model,
                    reason="Guard already exists for this parent/model combination",
                )

        # Build the guard lesson
        guard_id = new_id()
        guard = Lesson(
            symptom=f"Lesson '{parent.symptom[:80]}' harms model {model}",
            fix=f"Do not inject parent lesson {lesson_id} for model {model}",
            rationale=(
                f"Counterfactual evidence: baseline PASS → treatment FAIL when "
                f"lesson was injected. The model's default behavior is correct; "
                f"overriding it with this lesson degrades performance."
            ),
            source_episode_ids=parent.source_episode_ids[:3],
            task_id=parent.task_id,
            task_family=parent.task_family,
            confidence=0.9,  # guards start high-confidence
            scope=parent.scope,
            lesson_type=LessonType.NEGATIVE,
            parent_lesson_id=lesson_id,
            model_confidence={model: 0.95} if model else {},
            tags=["auto-guard", f"blocks:{lesson_id}"],
            id=guard_id,
        )

        # Embed and store the guard
        if self._embedder is not None and hasattr(self._embedder, "embed"):
            text = lesson.statement or f"{guard.symptom} {guard.fix}"
            vec = self._embedder.embed([text])[0]
        else:
            # Fallback: use a zero vector (will be updated on next consolidation)
            dim = getattr(self._store, "dim", 256)
            vec = [0.0] * dim

        self._store.add(guard, vec)

        logger.info(
            "Negative guard emitted: %s → blocks lesson %s for model %s",
            guard_id, lesson_id, model,
        )

        return GuardReport(
            guard_emitted=True,
            guard_id=guard_id,
            parent_lesson_id=lesson_id,
            model=model,
            reason="CAUSED_FAIL attribution triggered guard emission",
        )
