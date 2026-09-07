"""CreditAssigner — Bayesian confidence updates from counterfactual attribution.

Takes a CausalAttribution and updates the lesson's global and per-model
confidence tracks. This is the bridge between the Reflector (which classifies)
and the LessonStore (which persists).

Credit rules:
    CAUSED_PASS      → helped=True,  harmed=False  (positive credit)
    CAUSED_FAIL      → helped=False, harmed=True   (negative credit)
    INDEPENDENT_PASS → no update (redundant — lesson didn't cause the pass)
    INDEPENDENT_FAIL → no update (task too hard — lesson isn't to blame)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from ..models import Lesson
from ..store.lesson_store import SqliteLessonStore
from .reflector import CausalAttribution

logger = logging.getLogger(__name__)


class CreditType(str, Enum):
    POSITIVE = "positive"      # lesson caused a fix
    NEGATIVE = "negative"      # lesson caused harm
    NULL = "null"              # no causal signal (redundant or task too hard)


@dataclass(slots=True)
class CreditReport:
    """Structured report from a single credit assignment.

    Logs the posterior shift, the attribution rationale, and whether
    the confidence change triggered any threshold.
    """
    lesson_id: str
    model: str
    attribution: CausalAttribution
    credit_type: CreditType
    confidence_before: float
    confidence_after: float
    confidence_delta: float = 0.0
    task_id: str = ""
    seed: int = 0

    @property
    def is_significant(self) -> bool:
        """Whether the confidence moved by more than 0.05."""
        return abs(self.confidence_delta) > 0.05


class CreditAssigner:
    """Updates lesson confidence based on counterfactual attribution.

    Usage::

        assigner = CreditAssigner(lesson_store)
        report = assigner.assign(
            lesson_id="abc123",
            attribution=CausalAttribution.CAUSED_PASS,
            model="openai/gpt-4o-mini",
            task_id="acme-stream-consumer",
            seed=7,
        )
    """

    def __init__(self, lesson_store: SqliteLessonStore) -> None:
        self._store = lesson_store

    def assign(
        self,
        lesson_id: str,
        attribution: CausalAttribution,
        *,
        model: str = "",
        task_id: str = "",
        seed: int = 0,
    ) -> CreditReport:
        """Apply credit to a lesson based on causal attribution.

        Only CAUSED_PASS and CAUSED_FAIL trigger confidence updates.
        INDEPENDENT outcomes are logged but don't move the needle.
        """
        lesson = self._store.get(lesson_id)
        if lesson is None:
            logger.warning("Lesson %s not found in store — skipping credit", lesson_id)
            return CreditReport(
                lesson_id=lesson_id,
                model=model,
                attribution=attribution,
                credit_type=CreditType.NULL,
                confidence_before=0.5,
                confidence_after=0.5,
                task_id=task_id,
                seed=seed,
            )

        conf_before = lesson.bayesian_confidence(model=model)

        if attribution == CausalAttribution.CAUSED_PASS:
            credit_type = CreditType.POSITIVE
            self._store.update_confidence(
                lesson_id, helped=True, harmed=False, model=model
            )
        elif attribution == CausalAttribution.CAUSED_FAIL:
            credit_type = CreditType.NEGATIVE
            self._store.update_confidence(
                lesson_id, helped=False, harmed=True, model=model
            )
        else:
            # INDEPENDENT_PASS or INDEPENDENT_FAIL — no update
            credit_type = CreditType.NULL
            logger.debug(
                "Lesson %s: %s — no confidence update (null credit)",
                lesson_id, attribution.value,
            )
            return CreditReport(
                lesson_id=lesson_id,
                model=model,
                attribution=attribution,
                credit_type=credit_type,
                confidence_before=conf_before,
                confidence_after=conf_before,
                confidence_delta=0.0,
                task_id=task_id,
                seed=seed,
            )

        # Re-read the updated lesson
        updated = self._store.get(lesson_id)
        conf_after = updated.bayesian_confidence(model=model) if updated else conf_before
        delta = conf_after - conf_before

        report = CreditReport(
            lesson_id=lesson_id,
            model=model,
            attribution=attribution,
            credit_type=credit_type,
            confidence_before=conf_before,
            confidence_after=conf_after,
            confidence_delta=delta,
            task_id=task_id,
            seed=seed,
        )

        logger.info(
            "Credit assigned: lesson=%s model=%s %s → confidence %.3f→%.3f (Δ%+.3f)",
            lesson_id, model or "(global)", credit_type.value,
            conf_before, conf_after, delta,
        )
        return report
