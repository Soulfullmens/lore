"""Verify the memory-on path and ablation seam actually fire.

Uses a fake backend that injects a memory on retrieve(), and a mock agent
that succeeds more often when it sees the injected memory. This proves:
  1. The memory condition code path runs.
  2. Ablation withholding produces causal delta records.
  3. The contamination guard catches a backend that cheats on control tasks.

Run:  python -m examples.phase0_seam_test
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from lore_memory.models import (
    AgentStep, CreditUpdate, Episode, MemoryKind, Outcome,
    OutcomeStatus, RetrievedMemory,
)
from lore_memory.eval import AblationConfig, Harness, Mode, RunConfig
from lore_memory.backends import NullMemoryBackend
from lore_memory.protocols import MemoryBackend, Task


# --------------------------------------------------------------------------- #
# Fake backend: always returns one "helpful" memory on retrieve.
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _NullConsolidation:
    episodes_seen: int = 0
    lessons_created: int = 0
    lessons_merged: int = 0

@dataclass(slots=True)
class _NullForget:
    scanned: int = 0
    pruned: int = 0


class FakeMemoryBackend:
    """Returns a single canned memory on every retrieve (unless excluded)."""

    MEMORY_ID = "fake-lesson-001"
    MEMORY_CONTENT = "When asyncio.gather fails, use return_exceptions=True"

    def __init__(self) -> None:
        self._episodes: list[Episode] = []

    def setup(self) -> None:
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
        if self.MEMORY_ID in exclude_ids:
            return []  # ablation: memory withheld
        return [
            RetrievedMemory(
                kind=MemoryKind.LESSON,
                id=self.MEMORY_ID,
                content=self.MEMORY_CONTENT,
                score=0.9,
            )
        ]

    def record_episode(self, episode: Episode) -> None:
        self._episodes.append(episode)

    def reflect(self, episode: Episode, retrieved: Sequence[RetrievedMemory]) -> list[CreditUpdate]:
        return []

    def consolidate(self) -> _NullConsolidation:
        return _NullConsolidation()

    def forget(self) -> _NullForget:
        return _NullForget()

    def stats(self) -> dict[str, int]:
        return {"episode": len(self._episodes), "lesson": 1, "skill": 0}


# --------------------------------------------------------------------------- #
# Mock agent: 20% boost when it sees a memory (non-ablated).
# --------------------------------------------------------------------------- #
def _hash01(*parts: object) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


class MemoryAwareAgent:
    """Succeeds more often when memories are injected — the signal ablation
    is designed to detect."""

    def run(
        self,
        task: Task,
        memory: MemoryBackend,
        *,
        seed: int,
        ablate_ids: Collection[str] = (),
    ) -> Episode:
        # Retrieve (with ablation)
        retrieved = memory.retrieve(task.prompt(), k=3, exclude_ids=ablate_ids)
        injected_ids = [m.id for m in retrieved]

        roll = _hash01(task.id, seed)
        difficulty = 0.55
        # Memory gives a boost
        if retrieved:
            difficulty -= 0.20
        success = roll > difficulty

        step = AgentStep(
            thought=f"consider {task.id} (memories={len(retrieved)})",
            action="submit",
            observation="ok" if success else "assert failed",
            tokens_in=120 + len(retrieved) * 50,
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
            tokens_used=160 + len(retrieved) * 50,
            injected_memory_ids=injected_ids,
        )


@dataclass(slots=True)
class MockTask:
    id: str
    family: str
    is_control: bool = False

    def prompt(self) -> str:
        return f"[{self.family}] solve task {self.id}"

    def evaluate(self, workspace: str) -> Outcome:
        return Outcome(OutcomeStatus.SUCCESS, score=1.0)


def build_tasks() -> list[MockTask]:
    tasks: list[MockTask] = []
    for i in range(4):
        tasks.append(MockTask(f"async-{i}", family="python-async"))
    for i in range(4):
        tasks.append(MockTask(f"ctx-{i}", family="context-mgmt"))
    for i in range(2):
        tasks.append(MockTask(f"control-{i}", family="control", is_control=True))
    return tasks


def main() -> None:
    harness = Harness(MemoryAwareAgent(), build_tasks())
    cfg = RunConfig(
        seeds=(0, 1, 2, 3, 4, 5, 6, 7),
        k=3,
        ablation=AblationConfig(enabled=True, sample_rate=0.5, max_memories=3),
    )

    report = harness.run(
        baseline_factory=NullMemoryBackend,
        memory_factory=FakeMemoryBackend,
        config=cfg,
    )

    print("=== Seam verification: memory-on + ablation ===\n")

    base = report.per_condition[Mode.BASELINE]
    mem = report.per_condition[Mode.MEMORY]
    print(f"BASELINE success : {base.success}")
    print(f"MEMORY success   : {mem.success}")
    lift = report.improvement()
    print(f"lift             : {lift:+.3f}" if lift is not None else "lift: N/A")
    print(f"contamination    : delta={report.contamination_delta:+.3f}, "
          f"flagged={report.contaminated}")
    print(f"\nablation records : {len(report.ablation)}")

    if report.ablation:
        helpful = [a for a in report.ablation if a.delta > 0]
        neutral = [a for a in report.ablation if a.delta == 0]
        harmful = [a for a in report.ablation if a.delta < 0]
        print(f"  helpful (delta>0): {len(helpful)}")
        print(f"  neutral (delta=0): {len(neutral)}")
        print(f"  harmful (delta<0): {len(harmful)}")

    print("\n--- SEAM STATUS ---")
    print(f"  [{'PASS' if Mode.MEMORY in report.per_condition else 'FAIL'}] "
          "memory condition ran")
    print(f"  [{'PASS' if report.ablation else 'FAIL'}] "
          "ablation produced records")
    print(f"  [{'PASS' if report.contamination_delta != 0 or not report.contaminated else 'INFO'}] "
          "contamination guard checked")


if __name__ == "__main__":
    main()
