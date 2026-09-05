"""Phase 2 — Consolidation engine ("sleep" process).

Turns raw episodes into compact, reusable Lessons.  Runs offline between
task batches (the "sleep" in the wake/sleep metaphor).  Zero LLM cost in v1:
lessons are extracted by trajectory-diff analysis, not summarisation.

Components:
    EpisodeClusterer   — groups related episodes by task_id / task_family
    PatternExtractor   — diffs pass/fail trajectories to extract lessons
    LessonDeduplicator — prevents duplicate lessons, prefers generality
"""

from .clustering import EpisodeClusterer
from .extractor import PatternExtractor
from .dedup import LessonDeduplicator

__all__ = ["EpisodeClusterer", "PatternExtractor", "LessonDeduplicator"]
