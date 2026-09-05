"""The measurement harness — the thing you build *before* memory.

Phase 0's deliverable is not intelligence, it is a rigorous ruler. Every
later claim ('it learns', 'it's cheaper', 'this lesson caused the gain')
is only as trustworthy as this harness. So the three advanced seams are
built in from the first commit, even though their payloads arrive later:

1. Multi-seed runs with bootstrap CIs — no single-run screenshots.
2. Leave-one-out ablation — the causal-credit seam. Withhold one injected
   memory, re-run, measure the success delta. This is what lets Lore claim
   a *causal* verification signal instead of an LLM-judge guess.
3. Contamination control — 'no-memory-possible' tasks. If memory-on beats
   memory-off on control tasks, the gains are an artefact, not learning.

The harness is backend-agnostic: it drives any ``MemoryBackend`` (the
Phase 0 baseline is ``NullMemoryBackend``) through any ``Agent`` over any
set of ``Task``s.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from ..models import Episode, OutcomeStatus
from ..protocols import Agent, MemoryBackend, Task, Tracer
from ..protocols import NullTracer
from .stats import Estimate, bootstrap_ci, welch_t


class Mode(str, Enum):
    BASELINE = "baseline"   # memory-off control
    MEMORY = "memory"       # engine under test


@dataclass(slots=True)
class AblationConfig:
    """Controls the leave-one-out causal-credit pass.

    Ablation is expensive — re-running a task once per injected memory — so
    it is *sampled*, not run every attempt. ``sample_rate`` is the fraction
    of successful memory-on runs that get ablated; ``max_memories`` caps how
    many injected memories are individually withheld per sampled run."""

    enabled: bool = False
    sample_rate: float = 0.1
    max_memories: int = 3


@dataclass(slots=True)
class RunConfig:
    seeds: Sequence[int] = (0, 1, 2, 3, 4)   # N>=5 per data point by default
    k: int = 5                                # memories retrieved per task
    confidence: float = 0.95
    ablation: AblationConfig = field(default_factory=AblationConfig)


@dataclass(slots=True)
class RunRecord:
    """One (task, seed, mode) attempt, flattened for aggregation."""

    task_id: str
    task_family: str
    is_control: bool
    mode: Mode
    seed: int
    success: bool
    countable: bool          # False for infra ERROR — excluded from rates
    tokens: int
    duration_sec: float
    injected_ids: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass(slots=True)
class AblationRecord:
    """Causal contribution of one withheld memory on one task/seed.

    ``delta`` > 0 means withholding the memory *hurt* success — i.e. the
    memory was causally helpful. This is the raw signal Phase 3 turns into
    verified confidence, and it is immune to the LLM-judge's guesswork."""

    task_id: str
    seed: int
    memory_id: str
    success_with: bool
    success_without: bool

    @property
    def delta(self) -> float:
        return float(self.success_with) - float(self.success_without)


@dataclass(slots=True)
class ConditionSummary:
    mode: Mode
    success: Estimate
    tokens_per_success: Estimate
    n_attempts: int


@dataclass(slots=True)
class HarnessReport:
    per_condition: dict[Mode, ConditionSummary]
    contamination_delta: float          # memory-on minus memory-off on CONTROL tasks
    contaminated: bool                  # True if that delta is materially > 0
    ablation: list[AblationRecord] = field(default_factory=list)
    records: list[RunRecord] = field(default_factory=list)

    def improvement(self) -> float | None:
        """Success-rate lift of MEMORY over BASELINE on non-control tasks."""
        if Mode.MEMORY not in self.per_condition or Mode.BASELINE not in self.per_condition:
            return None
        return (
            self.per_condition[Mode.MEMORY].success.mean
            - self.per_condition[Mode.BASELINE].success.mean
        )


# --------------------------------------------------------------------------- #
# Backend factory: the harness builds a *fresh* backend per condition so
# baseline and memory runs never share state. A factory (not an instance)
# is what keeps the comparison clean.
# --------------------------------------------------------------------------- #
BackendFactory = Callable[[], MemoryBackend]


class Harness:
    def __init__(
        self,
        agent: Agent,
        tasks: Sequence[Task],
        *,
        tracer: Tracer | None = None,
    ) -> None:
        self._agent = agent
        self._tasks = list(tasks)
        self._tracer = tracer or NullTracer()

    # ----------------------------------------------------------------- #
    def run(
        self,
        baseline_factory: BackendFactory,
        memory_factory: BackendFactory | None,
        config: RunConfig | None = None,
    ) -> HarnessReport:
        """Run the full comparison.

        In Phase 0 ``memory_factory`` is ``None`` and only the baseline runs
        — producing the flat success line. From Phase 1 on, pass a real
        engine factory and the report fills in the lift, cost delta,
        contamination check and (if enabled) ablation deltas.
        """
        cfg = config or RunConfig()
        records: list[RunRecord] = []
        ablation: list[AblationRecord] = []

        records += self._run_condition(Mode.BASELINE, baseline_factory, cfg)
        if memory_factory is not None:
            mem_records, mem_ablation = self._run_memory_condition(memory_factory, cfg)
            records += mem_records
            ablation += mem_ablation

        return self._build_report(records, ablation, cfg)

    # ----------------------------------------------------------------- #
    def _run_condition(
        self, mode: Mode, factory: BackendFactory, cfg: RunConfig
    ) -> list[RunRecord]:
        backend = factory()
        backend.setup()
        out: list[RunRecord] = []
        try:
            for seed in cfg.seeds:
                for task in self._tasks:
                    ep = self._attempt(task, backend, seed, cfg)
                    out.append(self._to_record(task, mode, seed, ep))
        finally:
            backend.close()
        return out

    def _run_memory_condition(
        self, factory: BackendFactory, cfg: RunConfig
    ) -> tuple[list[RunRecord], list[AblationRecord]]:
        """Memory condition, with the learning loops and ablation seam live.

        Note the *ordering*: within a seed we let the engine consolidate
        between passes, because compounding is the whole point — episode i
        should be able to influence episode i+1. Baseline has no such loop,
        which is exactly the asymmetry we are trying to measure.
        """
        backend = factory()
        backend.setup()
        records: list[RunRecord] = []
        ablations: list[AblationRecord] = []
        rng = random.Random(1234)
        try:
            for seed in cfg.seeds:
                for task in self._tasks:
                    ep = self._attempt(task, backend, seed, cfg)
                    records.append(self._to_record(task, Mode.MEMORY, seed, ep))

                    # Post-task learning loops (no-ops until their phase).
                    retrieved = []  # Phase 1+ agents attach this to the episode
                    backend.reflect(ep, retrieved)

                    # ---- ablation seam --------------------------------- #
                    if (
                        cfg.ablation.enabled
                        and ep.outcome.status is OutcomeStatus.SUCCESS
                        and ep.injected_memory_ids
                        and rng.random() < cfg.ablation.sample_rate
                    ):
                        ablations += self._ablate(task, backend, seed, ep, cfg)

                # Offline consolidation once per seed-pass (the 'sleep').
                backend.consolidate()
                backend.forget()
        finally:
            backend.close()
        return records, ablations

    # ----------------------------------------------------------------- #
    def _attempt(
        self, task: Task, backend: MemoryBackend, seed: int, cfg: RunConfig
    ) -> Episode:
        with self._tracer.span("attempt", task=task.id, seed=seed):
            t0 = time.perf_counter()
            ep = self._agent.run(task, backend, seed=seed)
            ep.duration_sec = time.perf_counter() - t0
            backend.record_episode(ep)
            return ep

    def _ablate(
        self,
        task: Task,
        backend: MemoryBackend,
        seed: int,
        base_episode: Episode,
        cfg: RunConfig,
    ) -> list[AblationRecord]:
        """Leave-one-out: re-run the task withholding each injected memory."""
        out: list[AblationRecord] = []
        success_with = base_episode.outcome.status is OutcomeStatus.SUCCESS
        targets = base_episode.injected_memory_ids[: cfg.ablation.max_memories]
        for mem_id in targets:
            with self._tracer.span("ablate", task=task.id, memory=mem_id):
                # Same seed, so the only changed variable is the withheld memory.
                ep = self._agent.run(task, backend, seed=seed, ablate_ids=(mem_id,))
                out.append(
                    AblationRecord(
                        task_id=task.id,
                        seed=seed,
                        memory_id=mem_id,
                        success_with=success_with,
                        success_without=ep.outcome.status is OutcomeStatus.SUCCESS,
                    )
                )
        return out

    # ----------------------------------------------------------------- #
    @staticmethod
    def _to_record(task: Task, mode: Mode, seed: int, ep: Episode) -> RunRecord:
        return RunRecord(
            task_id=task.id,
            task_family=task.family,
            is_control=task.is_control,
            mode=mode,
            seed=seed,
            success=ep.outcome.is_success,
            countable=ep.outcome.is_countable,
            tokens=ep.tokens_used,
            duration_sec=ep.duration_sec,
            injected_ids=list(ep.injected_memory_ids),
            detail=ep.outcome.detail,
        )

    def _build_report(
        self,
        records: list[RunRecord],
        ablation: list[AblationRecord],
        cfg: RunConfig,
    ) -> HarnessReport:
        per_condition: dict[Mode, ConditionSummary] = {}
        for mode in {r.mode for r in records}:
            # Non-control, countable attempts drive the headline numbers.
            rows = [r for r in records if r.mode == mode and not r.is_control and r.countable]
            successes = [1.0 if r.success else 0.0 for r in rows]
            # tokens per *successful* task — the honest cost metric
            succ_tokens = [float(r.tokens) for r in rows if r.success and r.tokens > 0]
            per_condition[mode] = ConditionSummary(
                mode=mode,
                success=bootstrap_ci(successes, confidence=cfg.confidence),
                tokens_per_success=bootstrap_ci(succ_tokens, confidence=cfg.confidence),
                n_attempts=len(rows),
            )

        contamination_delta, contaminated = self._contamination(records)
        return HarnessReport(
            per_condition=per_condition,
            contamination_delta=contamination_delta,
            contaminated=contaminated,
            ablation=ablation,
            records=records,
        )

    @staticmethod
    def _contamination(records: list[RunRecord], threshold: float = 0.05) -> tuple[float, bool]:
        """On CONTROL tasks, memory should give *no* edge. Any material lift
        there means the base model already knew the answers — gains elsewhere
        are contaminated, not learned."""
        ctrl = [r for r in records if r.is_control and r.countable]
        mem = [1.0 if r.success else 0.0 for r in ctrl if r.mode == Mode.MEMORY]
        base = [1.0 if r.success else 0.0 for r in ctrl if r.mode == Mode.BASELINE]
        if not mem or not base:
            return 0.0, False
        delta = (sum(mem) / len(mem)) - (sum(base) / len(base))
        return delta, delta > threshold
