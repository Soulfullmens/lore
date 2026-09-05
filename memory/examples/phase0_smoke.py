"""Phase 0 smoke test — runs entirely offline, no API keys.

Proves three things before a single line of real memory exists:
  1. The harness drives a backend through an agent over a task set.
  2. Multi-seed aggregation with bootstrap CIs works.
  3. The ablation and contamination *seams* are exercised, not just present.

It uses a deterministic mock agent whose success is a fixed function of
(task, seed). That gives a stable, reproducible baseline line — exactly
what Phase 0 is supposed to output. Swap in a real LLM agent later and the
same harness produces the real curves.

Run:  python -m examples.phase0_smoke
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection
from dataclasses import dataclass

from lore_memory.models import AgentStep, Episode, Outcome, OutcomeStatus
from lore_memory.backends import NullMemoryBackend
from lore_memory.eval import AblationConfig, Harness, Mode, RunConfig
from lore_memory.protocols import MemoryBackend, Task


# --------------------------------------------------------------------------- #
# A tiny task type. `family` groups related tasks (the relatedness that makes
# learning measurable); `is_control` marks no-memory-possible tasks.
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class MockTask:
    id: str
    family: str
    is_control: bool = False
    difficulty: float = 0.5   # 0..1, higher = harder for the mock agent

    def prompt(self) -> str:
        return f"[{self.family}] solve task {self.id}"

    def evaluate(self, workspace: str) -> Outcome:  # not used by mock agent
        return Outcome(OutcomeStatus.SUCCESS, score=1.0)


def _hash01(*parts: object) -> float:
    """Deterministic pseudo-random float in [0,1) from the given parts."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class MockAgent:
    """Deterministic agent: succeeds when a stable hash beats the task
    difficulty. No memory effect (baseline). Reproducible per seed."""

    def run(
        self,
        task: Task,
        memory: MemoryBackend,
        *,
        seed: int,
        ablate_ids: Collection[str] = (),
    ) -> Episode:
        roll = _hash01(task.id, seed)
        success = roll > task.difficulty
        step = AgentStep(
            thought=f"consider {task.id}",
            action="submit",
            observation="ok" if success else "assert failed",
            tokens_in=120,
            tokens_out=40,
        )
        return Episode(
            task_id=task.id,
            task_family=task.family,
            task_description=task.prompt(),
            trajectory=[step],
            outcome=Outcome(
                OutcomeStatus.SUCCESS if success else OutcomeStatus.FAILURE,
                score=1.0 if success else 0.0,
            ),
            seed=seed,
            tokens_used=160,
            injected_memory_ids=[],   # baseline sees nothing
        )


def build_tasks() -> list[MockTask]:
    # Two related families (learnable) + one control family (must stay flat).
    tasks: list[MockTask] = []
    for i in range(4):
        tasks.append(MockTask(f"async-{i}", family="python-async", difficulty=0.55))
    for i in range(4):
        tasks.append(MockTask(f"ctx-{i}", family="context-mgmt", difficulty=0.5))
    for i in range(2):
        tasks.append(MockTask(f"control-{i}", family="control", is_control=True, difficulty=0.5))
    return tasks


def main() -> None:
    harness = Harness(MockAgent(), build_tasks())
    cfg = RunConfig(
        seeds=(0, 1, 2, 3, 4, 5, 6, 7),
        k=5,
        ablation=AblationConfig(enabled=True, sample_rate=0.2),
    )

    # Phase 0: baseline only (memory_factory=None -> flat line).
    report = harness.run(baseline_factory=NullMemoryBackend, memory_factory=None, config=cfg)

    base = report.per_condition[Mode.BASELINE]
    print("=== Phase 0 baseline (memory-off) ===")
    print(f"success rate      : {base.success}")
    print(f"tokens/success    : {base.tokens_per_success}")
    print(f"attempts (scored) : {base.n_attempts}")
    print(f"contamination delta: {report.contamination_delta:+.3f}  "
          f"(contaminated={report.contaminated})")
    print(f"ablation records  : {len(report.ablation)}  "
          "(0 expected at baseline: no memory to withhold)")
    print("\nThis flat line is the number every later phase must beat.")


if __name__ == "__main__":
    main()
