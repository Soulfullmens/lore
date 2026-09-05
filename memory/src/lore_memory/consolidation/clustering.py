"""Episode clustering for consolidation.

Groups related episodes so the pattern extractor can diff pass/fail
trajectories within a coherent cluster.  Two strategies in v1:

1. **task_id** (primary) — tightest, most reliable.  Lessons are scoped
   to one specific task.
2. **task_family** (fallback) — cross-task within a domain.  Discovers
   generalizable patterns (e.g., "asyncio cleanup gotchas" across
   multiple asyncio tasks).

Embedding-similarity clustering is deferred to a later version — it's
the noisiest and requires tuning.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from ..models import Episode, OutcomeStatus


@dataclass(slots=True)
class EpisodeCluster:
    """A group of related episodes with both successes and failures."""

    key: str                              # clustering key (task_id or family)
    scope: str                            # "task_id" or "task_family"
    successes: list[Episode] = field(default_factory=list)
    failures: list[Episode] = field(default_factory=list)

    @property
    def has_contrast(self) -> bool:
        """True if the cluster has both successes and failures to diff."""
        return bool(self.successes) and bool(self.failures)

    @property
    def success_rate(self) -> float:
        total = len(self.successes) + len(self.failures)
        return len(self.successes) / total if total else 0.0


class EpisodeClusterer:
    """Groups episodes into clusters for pattern extraction.

    Usage::

        clusterer = EpisodeClusterer()
        clusters = clusterer.cluster(episodes)
        # clusters with has_contrast=True are extractable
    """

    def cluster(
        self,
        episodes: list[Episode],
        *,
        min_successes: int = 1,
        min_failures: int = 1,
    ) -> list[EpisodeCluster]:
        """Cluster episodes and return only extractable clusters.

        An extractable cluster has at least ``min_successes`` successes
        and ``min_failures`` failures — enough contrast to diff.

        Returns clusters in two tiers:
        1. task_id clusters (tighter, preferred)
        2. task_family clusters (broader, fallback for tasks without
           enough per-task data)
        """
        # --- Tier 1: group by exact task_id ---
        by_task: dict[str, EpisodeCluster] = {}
        for ep in episodes:
            if ep.outcome.status is OutcomeStatus.ERROR:
                continue  # skip infra errors, they're noise
            key = ep.task_id
            if key not in by_task:
                by_task[key] = EpisodeCluster(key=key, scope="task_id")
            cluster = by_task[key]
            if ep.outcome.is_success:
                cluster.successes.append(ep)
            else:
                cluster.failures.append(ep)

        extractable: list[EpisodeCluster] = []
        covered_tasks: set[str] = set()

        for cluster in by_task.values():
            if (
                len(cluster.successes) >= min_successes
                and len(cluster.failures) >= min_failures
            ):
                extractable.append(cluster)
                covered_tasks.add(cluster.key)

        # --- Tier 2: group by task_family (fallback) ---
        # Only include episodes from tasks NOT already covered by tier 1
        by_family: dict[str, EpisodeCluster] = {}
        for ep in episodes:
            if ep.outcome.status is OutcomeStatus.ERROR:
                continue
            if ep.task_id in covered_tasks:
                continue  # already have a tight cluster for this task
            key = ep.task_family
            if not key:
                continue
            if key not in by_family:
                by_family[key] = EpisodeCluster(key=key, scope="task_family")
            cluster = by_family[key]
            if ep.outcome.is_success:
                cluster.successes.append(ep)
            else:
                cluster.failures.append(ep)

        for cluster in by_family.values():
            if (
                len(cluster.successes) >= min_successes
                and len(cluster.failures) >= min_failures
            ):
                extractable.append(cluster)

        return extractable
