"""Core data models for the Lore memory engine.

These are the shared contracts every layer speaks: the agent produces
``Episode``s, consolidation distills them into ``Lesson``s, and the
procedural layer promotes proven patterns into ``Skill``s. Nothing in
this module imports an agent framework or a storage backend — it is the
stable centre the rest of the system depends on.

Design notes
------------
* Every memory item carries an ``id`` and an ``embedding`` slot so the
  storage layer can treat them uniformly.
* ``Episode.injected_memory_ids`` is load-bearing: it records exactly
  which memories were visible during a run. Both LLM-judge reflection
  (Phase 3) and leave-one-out ablation (the causal credit seam) depend
  on knowing what the agent could have used.
* Confidence-bearing items (``Lesson``, ``Skill``) track
  ``times_applied`` / ``times_helped`` so verified utility is a first
  class, updatable quantity rather than a guess frozen at write time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import uuid

Vector = list[float]


def new_id() -> str:
    """Opaque, collision-resistant id. Hex so it is safe in filenames/URLs."""
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MemoryKind(str, Enum):
    EPISODE = "episode"
    LESSON = "lesson"
    SKILL = "skill"


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"   # agent ran, task assertions failed — counts against success rate
    ERROR = "error"       # infra/harness fault — EXCLUDED from success rate, never memorised as a lesson
    TIMEOUT = "timeout"


@dataclass(slots=True)
class Outcome:
    """The graded result of one task attempt.

    ``score`` supports partially-graded tasks; for binary tasks it is
    1.0/0.0 and mirrors ``is_success``. ``ERROR`` is deliberately distinct
    from ``FAILURE`` so infrastructure flakiness never pollutes either the
    success curve or the lesson corpus.
    """

    status: OutcomeStatus
    score: float = 0.0
    detail: str = ""
    asserts_passed: int = 0
    asserts_total: int = 0

    @property
    def is_success(self) -> bool:
        return self.status is OutcomeStatus.SUCCESS

    @property
    def is_countable(self) -> bool:
        """Whether this attempt belongs in success-rate statistics."""
        return self.status is not OutcomeStatus.ERROR


@dataclass(slots=True)
class AgentStep:
    """One (think -> act -> observe) triple in a trajectory."""

    thought: str
    action: str
    observation: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(slots=True)
class Episode:
    """A full agent trajectory on one task attempt — the raw material.

    Episodes are cheap and append-only. Most are never retrieved directly;
    consolidation is what turns them into compact, reusable knowledge.
    """

    task_id: str
    task_family: str
    task_description: str
    trajectory: list[AgentStep]
    outcome: Outcome
    seed: int
    tokens_used: int = 0
    duration_sec: float = 0.0
    # Which memories were visible to the agent on this run. Empty for
    # baseline/memory-off runs. Essential for reflection AND ablation.
    injected_memory_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    embedding: Vector | None = None


@dataclass(slots=True)
class Lesson:
    """A distilled, confidence-scored piece of semantic knowledge.

    Produced by consolidation, sharpened by verification. ``confidence``
    starts deliberately agnostic (0.5) and moves only as outcomes accrue,
    so a lesson extracted from a single lucky episode is never trusted
    until it has actually helped.

    The ``symptom`` / ``fix`` / ``rationale`` triple is the canonical
    representation.  It maps to agent-SEO (symptom-first HTML) and makes
    future LLM summarization a drop-in replacement — populate the same
    three fields with better prose, nothing downstream changes.
    """

    # --- core content (symptom-first schema) ---
    symptom: str = ""                # what went wrong / what the model gets wrong cold
    fix: str = ""                    # the concrete code or strategy change
    rationale: str = ""              # *why* the fix works (the transferable insight)

    # legacy single-string field, auto-populated from symptom/fix if empty
    statement: str = ""

    source_episode_ids: list[str] = field(default_factory=list)
    task_id: str = ""                # originating task id
    task_family: str = ""            # originating task family
    confidence: float = 0.5
    times_applied: int = 0
    times_helped: int = 0
    tags: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    last_used: datetime | None = None
    embedding: Vector | None = None

    def __post_init__(self) -> None:
        if not self.statement and (self.symptom or self.fix):
            parts = []
            if self.symptom:
                parts.append(f"Symptom: {self.symptom}")
            if self.fix:
                parts.append(f"Fix: {self.fix}")
            if self.rationale:
                parts.append(f"Rationale: {self.rationale}")
            self.statement = " | ".join(parts)

    def bayesian_confidence(self, prior_strength: float = 4.0) -> float:
        """Smoothed success rate — avoids 1.0/0.0 swings on tiny samples.

        Uses a Beta(prior_strength/2, prior_strength/2) prior centred at
        0.5 (Beta(2,2) by default), so a lesson needs repeated evidence
        to move far from neutral.  This prevents volatile 0%/100%
        confidence on tiny episode counts.
        """
        a = self.times_helped + prior_strength / 2
        b = (self.times_applied - self.times_helped) + prior_strength / 2
        return a / (a + b)


@dataclass(slots=True)
class Skill:
    """A reusable procedural pattern: 'when trigger, do actions'.

    Promoted from lessons that repeatedly co-occur with success. This is
    the Voyager-style skill library, generalised beyond one environment.
    """

    trigger_condition: str
    action_sequence: list[str]
    confidence: float = 0.5
    times_applied: int = 0
    times_helped: int = 0
    source_lesson_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    created_at: datetime = field(default_factory=utcnow)
    embedding: Vector | None = None

    @property
    def success_rate(self) -> float:
        return self.times_helped / self.times_applied if self.times_applied else 0.0


@dataclass(slots=True)
class RetrievedMemory:
    """A memory item returned by the read path, with retrieval provenance.

    ``kind`` + ``id`` let the harness thread ablation and credit updates
    back to the exact stored item. ``score`` is the retrieval rank score
    (relevance × confidence × recency once Phase 3/5 land).
    """

    kind: MemoryKind
    id: str
    content: str
    score: float
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class CreditUpdate:
    """Instruction to adjust one memory's verified-utility counters."""

    memory_id: str
    kind: MemoryKind
    applied: bool = True          # was it retrieved/injected this task?
    helped: bool = False          # did reflection/ablation credit it?
    causal_delta: float | None = None   # from ablation: Δ success when withheld
