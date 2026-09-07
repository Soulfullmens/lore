"""SequentialAnalyzer — early stopping via Bayesian Beta posterior analysis.

Monitors posterior probabilities to determine if a lesson has accumulated
enough evidence to be:
- PROMOTED:  P(confidence > tau_promote) >= 1 - alpha_risk
- DEMOTED:   P(confidence < tau_demote) >= 1 - alpha_risk
- REVIEW:    n_trials >= max_trials without meeting promote/demote threshold
- CONTINUE:  evidence is still ambiguous; collect more evaluation trials

Zero external dependencies: implements the regularized incomplete beta function
I_x(a, b) via Lentz's continued fraction method, with an automatic normal
approximation fallback when alpha or beta > 100.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum

from ..models import Lesson

logger = logging.getLogger(__name__)


class SequentialDecision(str, Enum):
    """Early stopping decision for a lesson."""

    PROMOTE = "promote"    # decisively helpful (high confidence)
    DEMOTE = "demote"      # decisively unhelpful or harmful
    CONTINUE = "continue"  # ambiguous, continue evaluation trials
    REVIEW = "review"      # max trials reached without decisive conclusion


def _betacf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 1e-10) -> float:
    """Continued fraction for incomplete beta function via modified Lentz method."""
    fpmin = 1e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < fpmin:
        d = fpmin
    d = 1.0 / d
    h = d

    for m in range(1, max_iter + 1):
        m2 = 2 * m
        # Even step
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        h *= d * c

        # Odd step
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < fpmin:
            d = fpmin
        c = 1.0 + aa / c
        if abs(c) < fpmin:
            c = fpmin
        d = 1.0 / d
        del_val = d * c
        h *= del_val

        if abs(del_val - 1.0) <= eps:
            break

    return h


def beta_cdf(x: float, a: float, b: float) -> float:
    """Compute the regularized incomplete beta function I_x(a, b) = P(Beta(a, b) <= x).

    Includes a normal approximation fallback when a > 100 or b > 100.
    """
    if a <= 0.0 or b <= 0.0:
        raise ValueError(f"Parameters a and b must be positive, got a={a}, b={b}")

    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # Normal approximation fallback for large parameters
    if a > 100.0 or b > 100.0:
        mu = a / (a + b)
        var = (a * b) / ((a + b) ** 2 * (a + b + 1.0))
        sigma = math.sqrt(var)
        if sigma <= 0.0:
            return 1.0 if x >= mu else 0.0
        z = (x - mu) / sigma
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    # Incomplete beta continued fraction
    l_bt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    bt = math.exp(l_bt)

    # Use symmetry relation for numerical stability
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    else:
        return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


@dataclass(slots=True)
class SequentialReport:
    """Full decision report for a lesson evaluation."""
    decision: SequentialDecision
    p_above_tau_promote: float
    p_below_tau_demote: float
    alpha: float
    beta: float
    n_trials: int
    tau_promote: float
    tau_demote: float
    confidence_level: float


class SequentialAnalyzer:
    """Bayesian sequential decision analyzer for lesson promotion/demotion.

    Usage::

        analyzer = SequentialAnalyzer(tau_promote=0.70, tau_demote=0.30)
        # 10 successes, 1 failure with Beta(2,2) prior -> alpha=12, beta=3
        report = analyzer.evaluate(alpha=12, beta=3, n_trials=11)
        assert report.decision == SequentialDecision.PROMOTE
    """

    def __init__(
        self,
        *,
        tau_promote: float = 0.70,
        tau_demote: float = 0.30,
        confidence_level: float = 0.95,
        max_trials: int = 30,
        prior_strength: float = 4.0,
    ) -> None:
        self.tau_promote = tau_promote
        self.tau_demote = tau_demote
        self.confidence_level = confidence_level
        self.max_trials = max_trials
        self.prior_strength = prior_strength

    def prob_confidence_above(self, threshold: float, a: float, b: float) -> float:
        """P(theta > threshold | Beta(a, b))."""
        return 1.0 - beta_cdf(threshold, a, b)

    def prob_confidence_below(self, threshold: float, a: float, b: float) -> float:
        """P(theta < threshold | Beta(a, b))."""
        return beta_cdf(threshold, a, b)

    def evaluate(
        self,
        a: float,
        b: float,
        *,
        n_trials: int = 0,
    ) -> SequentialReport:
        """Evaluate Beta(a, b) posterior against decision boundaries."""
        p_above = self.prob_confidence_above(self.tau_promote, a, b)
        p_below = self.prob_confidence_below(self.tau_demote, a, b)

        if p_above >= self.confidence_level:
            decision = SequentialDecision.PROMOTE
        elif p_below >= self.confidence_level:
            decision = SequentialDecision.DEMOTE
        elif n_trials >= self.max_trials:
            decision = SequentialDecision.REVIEW
        else:
            decision = SequentialDecision.CONTINUE

        return SequentialReport(
            decision=decision,
            p_above_tau_promote=p_above,
            p_below_tau_demote=p_below,
            alpha=a,
            beta=b,
            n_trials=n_trials,
            tau_promote=self.tau_promote,
            tau_demote=self.tau_demote,
            confidence_level=self.confidence_level,
        )

    def evaluate_lesson(
        self,
        lesson: Lesson,
        *,
        model: str = "",
    ) -> SequentialReport:
        """Extract posterior parameters from a Lesson and evaluate decision."""
        prior = self.prior_strength / 2.0
        if model and f"_applied_{model}" in lesson.model_confidence:
            applied = lesson.model_confidence.get(f"_applied_{model}", 0)
            helped = lesson.model_confidence.get(f"_helped_{model}", 0)
        else:
            applied = lesson.times_applied
            helped = lesson.times_helped

        a = helped + prior
        b = (applied - helped) + prior
        return self.evaluate(a, b, n_trials=applied)
