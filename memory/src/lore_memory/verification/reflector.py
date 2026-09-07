"""Reflector — counterfactual credit assignment via ablation comparison.

Compares the outcome of a treatment run (with lesson injected) against the
baseline outcome for the same seed to classify into one of four causal
quadrants:

    Baseline FAIL + Treatment PASS  →  CAUSED_PASS   (lesson fixed it)
    Baseline PASS + Treatment FAIL  →  CAUSED_FAIL   (lesson broke it)
    Baseline PASS + Treatment PASS  →  INDEPENDENT_PASS  (redundant)
    Baseline FAIL + Treatment FAIL  →  INDEPENDENT_FAIL  (task too hard)

This is the gold standard for causal attribution — most systems just
correlate; Lore can say "this lesson *caused* the fix."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from ..models import OutcomeStatus

logger = logging.getLogger(__name__)


class CausalAttribution(str, Enum):
    """The four counterfactual quadrants."""

    CAUSED_PASS = "caused_pass"          # baseline FAIL → treatment PASS
    CAUSED_FAIL = "caused_fail"          # baseline PASS → treatment FAIL
    INDEPENDENT_PASS = "independent_pass"  # both PASS — lesson is redundant
    INDEPENDENT_FAIL = "independent_fail"  # both FAIL — task too hard


class BaselineMissingError(Exception):
    """Raised when --verify needs a baseline outcome but none is cached.

    The fix is explicit: run without --skip-baseline first, or ensure the
    baseline cache is populated for every seed being verified.
    """

    def __init__(self, seed: int, task_id: str = "") -> None:
        context = f" for task '{task_id}'" if task_id else ""
        msg = (
            f"Seed {seed}{context} has no cached baseline. "
            f"Run without --skip-baseline first, or ensure baseline "
            f"cache is populated."
        )
        super().__init__(msg)
        self.seed = seed
        self.task_id = task_id


@dataclass(slots=True)
class SeedOutcome:
    """Outcome of a single (task_id, seed) run."""

    task_id: str
    seed: int
    success: bool
    status: OutcomeStatus = OutcomeStatus.SUCCESS
    detail: str = ""
    injected_lesson_ids: list[str] = field(default_factory=list)


class Reflector:
    """Compares treatment vs. baseline outcomes for counterfactual credit.

    Usage::

        reflector = Reflector()

        # Cache baseline results
        reflector.cache_baseline(SeedOutcome(task_id="t1", seed=0, success=False))

        # After treatment run
        attribution = reflector.compare(
            treatment=SeedOutcome(task_id="t1", seed=0, success=True),
        )
        # attribution == CausalAttribution.CAUSED_PASS
    """

    def __init__(self) -> None:
        # (task_id, seed) → SeedOutcome
        self._baseline_cache: dict[tuple[str, int], SeedOutcome] = {}

    def cache_baseline(self, outcome: SeedOutcome) -> None:
        """Store a baseline outcome for later counterfactual comparison."""
        key = (outcome.task_id, outcome.seed)
        self._baseline_cache[key] = outcome
        logger.debug("Cached baseline for %s seed=%d success=%s", outcome.task_id, outcome.seed, outcome.success)

    def cache_baselines(self, outcomes: list[SeedOutcome]) -> None:
        """Bulk cache baseline outcomes."""
        for o in outcomes:
            self.cache_baseline(o)

    def has_baseline(self, task_id: str, seed: int) -> bool:
        """Check if a baseline outcome is cached for this (task, seed)."""
        return (task_id, seed) in self._baseline_cache

    def get_baseline(self, task_id: str, seed: int) -> SeedOutcome | None:
        """Return cached baseline outcome, or None."""
        return self._baseline_cache.get((task_id, seed))

    def compare(
        self,
        treatment: SeedOutcome,
        *,
        require_baseline: bool = True,
    ) -> CausalAttribution:
        """Compare treatment outcome against cached baseline.

        Args:
            treatment: The outcome of the treatment run (lesson injected).
            require_baseline: If True (default), raises BaselineMissingError
                when no baseline is cached. If False, returns INDEPENDENT_FAIL
                as a conservative default.

        Returns:
            CausalAttribution — one of the four quadrants.

        Raises:
            BaselineMissingError: When baseline is missing and require_baseline=True.
        """
        key = (treatment.task_id, treatment.seed)
        baseline = self._baseline_cache.get(key)

        if baseline is None:
            if require_baseline:
                raise BaselineMissingError(treatment.seed, treatment.task_id)
            logger.warning(
                "No baseline for %s seed=%d — defaulting to INDEPENDENT_FAIL",
                treatment.task_id, treatment.seed,
            )
            return CausalAttribution.INDEPENDENT_FAIL

        baseline_pass = baseline.success
        treatment_pass = treatment.success

        if not baseline_pass and treatment_pass:
            attribution = CausalAttribution.CAUSED_PASS
        elif baseline_pass and not treatment_pass:
            attribution = CausalAttribution.CAUSED_FAIL
        elif baseline_pass and treatment_pass:
            attribution = CausalAttribution.INDEPENDENT_PASS
        else:
            attribution = CausalAttribution.INDEPENDENT_FAIL

        logger.info(
            "Credit assignment: %s seed=%d — baseline=%s treatment=%s → %s",
            treatment.task_id, treatment.seed,
            "PASS" if baseline_pass else "FAIL",
            "PASS" if treatment_pass else "FAIL",
            attribution.value,
        )
        return attribution

    @property
    def cached_seed_count(self) -> int:
        """Number of cached baseline outcomes."""
        return len(self._baseline_cache)
