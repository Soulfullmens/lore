"""Statistical rigour for the harness.

LLM agents are stochastic, so a single-run graph is noise dressed as a
result. Everything the benchmark reports is an aggregate over multiple
seeds with a confidence interval. This module is intentionally
dependency-free (pure stdlib) so it runs anywhere the harness runs.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(slots=True)
class Estimate:
    """A point estimate with a confidence interval and sample size."""

    mean: float
    lo: float
    hi: float
    n: int

    @property
    def half_width(self) -> float:
        return (self.hi - self.lo) / 2

    def __str__(self) -> str:
        return f"{self.mean:.3f} [{self.lo:.3f}, {self.hi:.3f}] (n={self.n})"


def bootstrap_ci(
    values: Sequence[float],
    *,
    confidence: float = 0.95,
    iterations: int = 10_000,
    seed: int = 0,
) -> Estimate:
    """Percentile bootstrap CI for the mean.

    Works for binary success (0/1 values -> proportion CI) and for
    continuous metrics (tokens, latency) alike, and makes no normality
    assumption — which matters for skewed, small-n LLM eval data.
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return Estimate(0.0, 0.0, 0.0, 0)
    if n == 1:
        return Estimate(vals[0], vals[0], vals[0], 1)

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(iterations):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    alpha = 1.0 - confidence
    lo = means[int((alpha / 2) * iterations)]
    hi = means[min(iterations - 1, int((1 - alpha / 2) * iterations))]
    return Estimate(mean=statistics.fmean(vals), lo=lo, hi=hi, n=n)


def welch_t(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Welch's t statistic and degrees of freedom for two samples.

    Used to answer 'is memory-on genuinely better than baseline, or is the
    gap inside the noise?' Returns ``(t, df)``; pair with a t-table or
    ``statistics``-based p-value at call sites that need a hard threshold.
    """
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0.0, 0.0
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    va, vb = statistics.variance(a), statistics.variance(b)
    sa, sb = va / na, vb / nb
    denom = math.sqrt(sa + sb)
    if denom == 0:
        return 0.0, 0.0
    t = (ma - mb) / denom
    df = (sa + sb) ** 2 / ((sa**2) / (na - 1) + (sb**2) / (nb - 1))
    return t, df
