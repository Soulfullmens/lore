"""Framework-agnostic contracts for the Lore memory engine.

The whole adoption thesis lives here: the engine defines *protocols*, and
agent frameworks (LangGraph, CrewAI, vanilla loops) become thin adapters
against them. Nothing here imports a framework, a storage driver, or an
LLM SDK — those are all injected.

The four seams the plan committed to are visible directly in these
signatures:

* **Ablation / causal credit** — ``MemoryBackend.retrieve`` takes
  ``exclude_ids``. The harness withholds one injected memory and re-runs
  to measure its causal contribution. No later refactor needed.
* **Multi-seed eval** — ``Agent.run`` takes an explicit ``seed`` so runs
  are reproducible and variance is measurable.
* **Observability** — every backend accepts a ``Tracer``; the default is
  a no-op, so tracing is a seam, not a dependency.
* **Pluggable storage** — ``StorageBackend`` is separate from
  ``MemoryBackend``; the default SQLite+sqlite-vec impl and any future
  pgvector/Qdrant impl satisfy the same interface.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from contextlib import contextmanager
from typing import Iterator, Protocol, runtime_checkable

from .models import (
    CreditUpdate,
    Episode,
    MemoryKind,
    Outcome,
    RetrievedMemory,
    Vector,
)


# --------------------------------------------------------------------------- #
# Observability seam
# --------------------------------------------------------------------------- #
@runtime_checkable
class Tracer(Protocol):
    """Minimal span interface. A real impl wraps OpenTelemetry; the default
    is a no-op so nothing in the engine depends on a tracing backend."""

    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        ...


class NullTracer:
    """Default tracer: does nothing, costs nothing."""

    @contextmanager
    def span(self, name: str, **attributes: object) -> Iterator[None]:
        yield


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turns text into vectors. Local (sentence-transformers) or API-backed;
    the engine never assumes which."""

    @property
    def dim(self) -> int:
        ...

    def embed(self, texts: Sequence[str]) -> list[Vector]:
        ...


# --------------------------------------------------------------------------- #
# Storage layer (low level)
# --------------------------------------------------------------------------- #
@runtime_checkable
class StorageBackend(Protocol):
    """Persistence + vector search, one namespace per ``MemoryKind``.

    Kept deliberately dumb: it stores rows and does nearest-neighbour
    search. All intelligence (what to write, what to trust, what to
    forget) lives in ``MemoryBackend``, so swapping SQLite for Qdrant
    changes nothing above this line.
    """

    def setup(self) -> None: ...
    def close(self) -> None: ...

    def upsert(
        self,
        kind: MemoryKind,
        id: str,
        payload: dict[str, object],
        embedding: Vector | None,
    ) -> None: ...

    def get(self, kind: MemoryKind, id: str) -> dict[str, object] | None: ...

    def search(
        self,
        kind: MemoryKind,
        embedding: Vector,
        k: int,
        *,
        exclude_ids: Collection[str] = (),
    ) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(id, similarity)`` pairs, honouring
        ``exclude_ids`` — the ablation seam at the storage level."""
        ...

    def delete(self, kind: MemoryKind, ids: Collection[str]) -> None: ...
    def count(self, kind: MemoryKind) -> int: ...
    def iter_ids(self, kind: MemoryKind) -> Iterator[str]: ...


# --------------------------------------------------------------------------- #
# Memory engine (high level) — the thing agents talk to
# --------------------------------------------------------------------------- #
@runtime_checkable
class MemoryBackend(Protocol):
    """The engine. A memory-off baseline and the full compounding engine
    are two implementations of this identical surface, so the harness runs
    byte-identical code paths for both — the only honest way to attribute
    a difference to memory."""

    def setup(self) -> None: ...
    def close(self) -> None: ...

    # ---- read path ------------------------------------------------------ #
    def retrieve(
        self,
        query: str,
        *,
        k: int = 5,
        exclude_ids: Collection[str] = (),
    ) -> list[RetrievedMemory]:
        """Rank and return memories for ``query``.

        ``exclude_ids`` is the causal-credit seam: pass a memory's id to
        withhold it, re-run the task, and measure the success delta. In
        normal operation it is empty.
        """
        ...

    # ---- write path ----------------------------------------------------- #
    def record_episode(self, episode: Episode) -> None:
        """Persist a completed trajectory (append-only, hot path, cheap)."""
        ...

    # ---- learning loops (implemented progressively across phases) ------- #
    def reflect(
        self,
        episode: Episode,
        retrieved: Sequence[RetrievedMemory],
    ) -> list[CreditUpdate]:
        """Post-task credit assignment (Phase 3). Given what was retrieved
        and how the task ended, decide which memories to reward. Phase 0/1
        return ``[]``."""
        ...

    def consolidate(self) -> ConsolidationReport:
        """Offline 'sleep' distillation of episodes into lessons (Phase 2).
        Runs off the hot path. Phase 0/1 are no-ops."""
        ...

    def forget(self) -> ForgetReport:
        """Value-based pruning (Phase 4). Phase 0–3 are no-ops."""
        ...

    def stats(self) -> dict[str, int]:
        """Cheap counts per kind — feeds the storage-growth graph."""
        ...


# --------------------------------------------------------------------------- #
# Reports returned by the learning loops
# --------------------------------------------------------------------------- #
class ConsolidationReport(Protocol):
    episodes_seen: int
    lessons_created: int
    lessons_merged: int


class ForgetReport(Protocol):
    scanned: int
    pruned: int


# --------------------------------------------------------------------------- #
# Task + Agent contracts (used by the eval harness)
# --------------------------------------------------------------------------- #
@runtime_checkable
class Task(Protocol):
    """One repeatable benchmark task.

    ``family`` groups related tasks — the relatedness that makes learning
    *measurable*, since a lesson from one family member should transfer to
    another. ``is_control`` marks 'no-memory-possible' tasks used to catch
    contamination: if memory-on beats memory-off *here*, the gains are not
    real learning."""

    @property
    def id(self) -> str: ...
    @property
    def family(self) -> str: ...
    @property
    def is_control(self) -> bool: ...

    def prompt(self) -> str:
        """The task statement handed to the agent."""
        ...

    def evaluate(self, workspace: str) -> Outcome:
        """Grade the agent's result deterministically (asserts / eval cmd)."""
        ...


@runtime_checkable
class Agent(Protocol):
    """The thin reference loop. It owns retrieval — it calls
    ``memory.retrieve`` itself — so ablation threads harness -> agent ->
    memory via ``ablate_ids`` without the harness reaching inside the loop."""

    def run(
        self,
        task: Task,
        memory: MemoryBackend,
        *,
        seed: int,
        ablate_ids: Collection[str] = (),
    ) -> Episode:
        """Solve ``task`` once, deterministically for a given ``seed``.

        The returned ``Episode`` must set ``injected_memory_ids`` to exactly
        the memories the agent saw, so credit assignment and ablation have
        ground truth. ``ablate_ids`` is forwarded to ``retrieve`` as
        ``exclude_ids``."""
        ...
