"""The memory-off baseline.

This is not a stub — it is a first-class implementation of ``MemoryBackend``
whose job is to do nothing intelligently. Because it satisfies the exact
same protocol as the real engine, the harness executes an identical code
path for baseline and memory runs. Any measured difference is therefore
attributable to memory and not to a divergent control path.

Phase 0 ships only this backend. Its benchmark output is the flat line
every later phase has to beat.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from ..models import CreditUpdate, Episode, RetrievedMemory


@dataclass(slots=True)
class _NullConsolidationReport:
    episodes_seen: int = 0
    lessons_created: int = 0
    lessons_merged: int = 0


@dataclass(slots=True)
class _NullForgetReport:
    scanned: int = 0
    pruned: int = 0


class NullMemoryBackend:
    """Memory-off control. Retrieves nothing, learns nothing, forgets
    nothing — but records episodes so the harness can still report token
    and success statistics on identical plumbing."""

    def __init__(self) -> None:
        self._episodes: list[Episode] = []

    def setup(self) -> None:  # noqa: D401 - protocol method
        pass

    def close(self) -> None:
        self._episodes.clear()

    def retrieve(
        self,
        query: str,
        *,
        k: int = 5,
        exclude_ids: Collection[str] = (),
    ) -> list[RetrievedMemory]:
        return []

    def record_episode(self, episode: Episode) -> None:
        # Kept in memory only; the baseline never reads them back.
        self._episodes.append(episode)

    def reflect(
        self,
        episode: Episode,
        retrieved: Sequence[RetrievedMemory],
    ) -> list[CreditUpdate]:
        return []

    def consolidate(self) -> _NullConsolidationReport:
        return _NullConsolidationReport()

    def forget(self) -> _NullForgetReport:
        return _NullForgetReport()

    def stats(self) -> dict[str, int]:
        return {"episode": len(self._episodes), "lesson": 0, "skill": 0}
