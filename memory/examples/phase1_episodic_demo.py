"""Phase 1 offline proof — no API key.

Reconciled against the real models.py: Episodes use task_description (not
query_text), Outcome is a dataclass with OutcomeStatus, RetrievedMemory
uses MemoryKind.EPISODE + content string + metadata dict.

Proves the episodic memory path end to end with the HashEmbedder:
  1. record_episode() stores episodes (persisted in SQLite)
  2. retrieve() returns the RELATED past episode for a family sibling
     (safe_gather -> safe_gather_named) and NOT the unrelated control
  3. outcome filtering: failures are not injected by default
  4. ablation seam: exclude_ids removes the target -> retrieval changes
  5. persistence round-trip: reopen a file-backed store and read it back

Run: python -m examples.phase1_episodic_demo
"""
from __future__ import annotations

import os
import tempfile

from lore_memory.models import (
    AgentStep,
    Episode,
    MemoryKind,
    Outcome,
    OutcomeStatus,
)
from lore_memory.store import (
    EpisodicMemoryBackend,
    HashEmbedder,
    SqliteEpisodeStore,
)


def _make_episode(
    id_: str,
    task_id: str,
    family: str,
    description: str,
    status: OutcomeStatus = OutcomeStatus.SUCCESS,
) -> Episode:
    """Build a minimal Episode with the real constructor."""
    return Episode(
        task_id=task_id,
        task_family=family,
        task_description=description,
        trajectory=[AgentStep(thought="solved it", action="fix", observation="ok")],
        outcome=Outcome(status=status, score=1.0 if status == OutcomeStatus.SUCCESS else 0.0),
        seed=0,
        tokens_used=160,
        id=id_,
    )


def main() -> None:
    emb = HashEmbedder(dim=256)
    store = SqliteEpisodeStore(":memory:", dim=emb.dim)
    mem = EpisodicMemoryBackend(store=store, embedder=emb)
    mem.setup()

    # 1) Record three episodes: related success, unrelated success, related failure
    mem.record_episode(_make_episode(
        "e1", "async-safe-gather", "python-async",
        "python asyncio gather concurrent tasks one raises exception others lost "
        "return_exceptions collect results safely",
    ))
    mem.record_episode(_make_episode(
        "e2", "string-reverse", "general",
        "reverse a string in python return characters in opposite order",
    ))
    mem.record_episode(_make_episode(
        "e3", "async-timeout", "python-async",
        "python asyncio gather tasks exception handling wait_for timeout",
        status=OutcomeStatus.FAILURE,
    ))

    assert store.count() == 3, f"expected 3 episodes, got {store.count()}"
    print(f"recorded 3 episodes (store count={store.count()})")

    # 2) Family sibling query -> should surface e1 (related), not e2 (control)
    query = ("python asyncio gather named coroutines dict one fails others "
             "should still return return_exceptions")
    hits = mem.retrieve(query, k=2)
    ids = [h.id for h in hits]
    print(f"\nquery: safe_gather_named (family sibling)")
    for h in hits:
        task_id = h.metadata.get("task_id", "?")
        print(f"   -> {h.id:4}  score={h.score:.3f}  task={task_id}  kind={h.kind.value}")
    assert ids and ids[0] == "e1", f"expected e1 top, got {ids}"
    assert "e2" not in ids[:1], "control leaked to top rank"
    print("   PASS: related episode retrieved, control not top-ranked")

    # 3) Outcome filter: the FAILURE (e3) must not appear (default = successes only)
    all_hits = mem.retrieve(query, k=5)
    assert all(h.id != "e3" for h in all_hits), "failure got injected"
    print("   PASS: failed episode not injected (outcome filter works)")

    # 4) Ablation seam: exclude e1 -> top result must change
    ablated = mem.retrieve(query, k=1, exclude_ids=["e1"])
    ablated_ids = [h.id for h in ablated]
    print(f"\nablation exclude=e1 -> top now: {ablated_ids}")
    assert not ablated or ablated[0].id != "e1", "ablation failed to exclude target"
    print("   PASS: ablation seam removes the target episode")

    # 5) Persistence round-trip
    tmp = os.path.join(tempfile.mkdtemp(), "lore_phase1.db")
    s1 = SqliteEpisodeStore(tmp, dim=emb.dim)
    m1 = EpisodicMemoryBackend(store=s1, embedder=emb)
    m1.setup()
    m1.record_episode(_make_episode(
        "p1", "async-safe-gather", "python-async",
        "asyncio gather return_exceptions",
    ))
    s1.close()
    s2 = SqliteEpisodeStore(tmp, dim=emb.dim)
    print(f"\npersistence: reopened store count={s2.count()}")
    assert s2.count() == 1, "episode did not persist across reopen"
    s2.close()
    print("   PASS: SQLite persistence round-trips")

    # 6) Stats
    print(f"\nstats: {mem.stats()}")
    assert mem.stats()["episode"] == 3

    print("\nALL PHASE 1 CHECKS PASSED")


if __name__ == "__main__":
    main()
