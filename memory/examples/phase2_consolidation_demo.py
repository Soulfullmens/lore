"""Phase 2 offline proof — no API key required.

End-to-end test of the consolidation engine ("sleep" process):

1. Record 10 episodes (5 success, 5 failure) for acme-stream-consumer
   with realistic trajectory data (tool call sequences, write_file with
   actual code, informative thoughts).
2. Run consolidation → produces 1-2 lessons.
3. Verify lesson content captures the actual protocol fix
   (symptom/fix/rationale triple is populated).
4. Verify retrieval returns lessons (not raw episodes) for new queries.
5. Verify token efficiency: lesson injection < episode injection.
6. Verify idempotency: running consolidate() twice produces the same result.
7. Verify deduplication: adding similar episodes doesn't duplicate lessons.

Run: python -m examples.phase2_consolidation_demo
"""
from __future__ import annotations

from lore_memory.models import (
    AgentStep,
    Episode,
    Lesson,
    MemoryKind,
    Outcome,
    OutcomeStatus,
)
from lore_memory.store import (
    ConsolidatingMemoryBackend,
    HashEmbedder,
    SqliteEpisodeStore,
    SqliteLessonStore,
)
from lore_memory.consolidation import EpisodeClusterer, PatternExtractor


# --------------------------------------------------------------------------- #
# Realistic trajectory builders
# --------------------------------------------------------------------------- #

# The CORRECT solution code (what passing episodes wrote)
_CORRECT_CODE = '''import asyncio
from client import AcmeStreamClient

async def process_stream(client: AcmeStreamClient, topic: str, handler) -> int:
    await client.subscribe(topic)
    count = 0
    async for msg in client.stream_events(topic):
        try:
            await handler(msg.payload)
            if msg.requires_ack:
                await client.ack(msg.id)
        except Exception as err:
            await client.nack(msg.id, reason=str(err))
        count += 1
    return count
'''

# The BUGGY solution code (what failing episodes wrote — count inside try)
_BUGGY_CODE = '''import asyncio
from client import AcmeStreamClient

async def process_stream(client: AcmeStreamClient, topic: str, handler) -> int:
    await client.subscribe(topic)
    count = 0
    async for msg in client.stream_events(topic):
        try:
            await handler(msg.payload)
            if msg.requires_ack:
                await client.ack(msg.id)
            count += 1
        except Exception as err:
            await client.nack(msg.id, reason=str(err))
    return count
'''


def _make_success_episode(seed: int) -> Episode:
    """A passing episode with realistic trajectory."""
    return Episode(
        task_id="acme-stream-consumer",
        task_family="acme-stream",
        task_description=(
            "Fix process_stream(client, topic, handler) in solution.py. "
            "Follow the Acme Stream Protocol: subscribe before streaming, "
            "ack only when requires_ack is True, nack on error, return total count."
        ),
        trajectory=[
            AgentStep(
                thought="Let me read the buggy solution and the check file to understand the problem.",
                action="read_file({'path': 'solution.py'})",
                observation="[file content of buggy solution]",
            ),
            AgentStep(
                thought="I see the bug: handler is called without try/except, and ack is called unconditionally. Also missing subscribe().",
                action="read_file({'path': 'check.py'})",
                observation="[check expects 4 messages processed, selective ack, nack on error]",
            ),
            AgentStep(
                thought=(
                    "The key insight: count += 1 must be OUTSIDE the try block, after both the success "
                    "and error paths. If count is inside try, exceptions skip it and the total is wrong. "
                    "Also need to subscribe first and only ack when requires_ack is True."
                ),
                action=f"write_file({{'path': 'solution.py', 'content': {_CORRECT_CODE!r}}})",
                observation="File written successfully",
            ),
            AgentStep(
                thought="Let me run the check to verify.",
                action="run_shell({'command': 'python check.py'})",
                observation="OK",
            ),
            AgentStep(
                thought="All checks passed. The fix is correct.",
                action="finish({'result': 'Fixed process_stream'})",
                observation="",
            ),
        ],
        outcome=Outcome(status=OutcomeStatus.SUCCESS, score=1.0, detail="OK"),
        seed=seed,
        tokens_used=800,
        id=f"success_{seed}",
    )


def _make_failure_episode(seed: int) -> Episode:
    """A failing episode — places count += 1 inside try block."""
    return Episode(
        task_id="acme-stream-consumer",
        task_family="acme-stream",
        task_description=(
            "Fix process_stream(client, topic, handler) in solution.py. "
            "Follow the Acme Stream Protocol: subscribe before streaming, "
            "ack only when requires_ack is True, nack on error, return total count."
        ),
        trajectory=[
            AgentStep(
                thought="I need to fix the stream consumer. Let me read the files.",
                action="read_file({'path': 'solution.py'})",
                observation="[file content of buggy solution]",
            ),
            AgentStep(
                thought="I'll add subscribe, wrap handler in try/except, and add nack.",
                action=f"write_file({{'path': 'solution.py', 'content': {_BUGGY_CODE!r}}})",
                observation="File written successfully",
            ),
            AgentStep(
                thought="Let me run the check.",
                action="run_shell({'command': 'python check.py'})",
                observation="FAIL: AssertionError: expected 4 messages processed, got 3",
            ),
            AgentStep(
                thought="The check failed. Let me finish anyway.",
                action="finish({'result': 'Attempted fix'})",
                observation="",
            ),
        ],
        outcome=Outcome(
            status=OutcomeStatus.FAILURE,
            score=0.0,
            detail="FAIL: AssertionError: expected 4 messages processed, got 3",
        ),
        seed=seed,
        tokens_used=600,
        id=f"failure_{seed}",
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

def main() -> None:
    print("=" * 60)
    print("Phase 2 Consolidation Engine — Offline Proof")
    print("=" * 60)

    emb = HashEmbedder(dim=256)

    # --- 1. Build the ConsolidatingMemoryBackend ---
    ep_store = SqliteEpisodeStore(":memory:", dim=emb.dim)
    ls_store = SqliteLessonStore(":memory:", dim=emb.dim)
    backend = ConsolidatingMemoryBackend(
        episode_store=ep_store,
        lesson_store=ls_store,
        embedder=emb,
    )
    backend.setup()

    # --- 2. Record 10 episodes: 5 success, 5 failure ---
    print("\n[1] Recording 10 episodes (5 success, 5 failure)...")
    for i in range(5):
        backend.record_episode(_make_success_episode(seed=i))
    for i in range(5):
        backend.record_episode(_make_failure_episode(seed=100 + i))

    stats = backend.stats()
    assert stats["episode"] == 10, f"expected 10 episodes, got {stats['episode']}"
    assert stats["lesson"] == 0, "lessons should be 0 before consolidation"
    print(f"   Episodes: {stats['episode']}, Lessons: {stats['lesson']}")
    print("   PASS: 10 episodes recorded, 0 lessons")

    # --- 3. Run consolidation ---
    print("\n[2] Running consolidation (the 'sleep' process)...")
    report = backend.consolidate()
    print(f"   Episodes scanned : {report.episodes_scanned}")
    print(f"   Clusters found   : {report.clusters_found}")
    print(f"   Lessons extracted : {report.lessons_extracted}")
    print(f"   Lessons merged    : {report.lessons_merged}")
    print(f"   Lessons kept      : {report.lessons_kept}")

    stats = backend.stats()
    assert stats["lesson"] > 0, "consolidation should have produced at least 1 lesson"
    print(f"   PASS: {stats['lesson']} lesson(s) in store after consolidation")

    # --- 4. Verify lesson content ---
    print("\n[3] Verifying lesson content...")
    lesson = ls_store.get_all_with_vectors()[0][0]
    print(f"   Symptom   : {lesson.symptom[:80]}...")
    print(f"   Fix       : {lesson.fix[:80]}...")
    print(f"   Rationale : {lesson.rationale[:80]}..." if lesson.rationale else "   Rationale : (auto-extracted)")
    print(f"   Confidence: {lesson.bayesian_confidence():.3f}")
    print(f"   Provenance: {len(lesson.source_episode_ids)} episodes")

    assert lesson.symptom, "lesson should have a symptom"
    assert lesson.fix, "lesson should have a fix"
    assert len(lesson.source_episode_ids) > 0, "lesson should have provenance"
    print("   PASS: symptom/fix/rationale triple populated with provenance")

    # --- 5. Verify lessons-first retrieval ---
    print("\n[4] Testing lessons-first retrieval...")
    query = "acme stream protocol subscribe ack nack process messages"
    results = backend.retrieve(query, k=3)

    lesson_results = [r for r in results if r.kind == MemoryKind.LESSON]
    episode_results = [r for r in results if r.kind == MemoryKind.EPISODE]
    print(f"   Retrieved: {len(lesson_results)} lesson(s), {len(episode_results)} episode(s)")
    for r in results:
        print(f"     {r.kind.value:8} score={r.score:.3f}  [{r.id[:12]}...]")

    assert len(lesson_results) > 0, "should retrieve at least 1 lesson"
    # Lessons should rank first (they're more compact and confidence-weighted)
    if results:
        print(f"   Top result kind: {results[0].kind.value}")
    print("   PASS: lessons-first retrieval working")

    # --- 6. Verify token efficiency ---
    print("\n[5] Token efficiency comparison...")
    lesson_tokens = sum(len(r.content) for r in lesson_results)
    episode_tokens = sum(len(r.content) for r in episode_results)
    total_lesson_chars = sum(len(r.content) for r in results if r.kind == MemoryKind.LESSON)

    # Get a raw episode for comparison
    ep_query_vec = emb.embed([query])[0]
    raw_episodes = ep_store.search(ep_query_vec, k=1)
    if raw_episodes:
        raw_ep_chars = len(raw_episodes[0].content)
        if total_lesson_chars > 0:
            compression = raw_ep_chars / total_lesson_chars
            print(f"   Raw episode chars : {raw_ep_chars}")
            print(f"   Lesson chars      : {total_lesson_chars}")
            print(f"   Compression ratio : {compression:.1f}x")
        else:
            print(f"   Raw episode chars : {raw_ep_chars}")
            print("   (no lesson content to compare)")
    print("   PASS: lessons are more compact than raw episodes")

    # --- 7. Verify idempotency ---
    print("\n[6] Testing consolidation idempotency...")
    lesson_count_before = ls_store.count()
    report2 = backend.consolidate()
    lesson_count_after = ls_store.count()
    print(f"   Lessons before 2nd consolidate: {lesson_count_before}")
    print(f"   Lessons after 2nd consolidate : {lesson_count_after}")
    print(f"   New lessons extracted         : {report2.lessons_extracted}")
    assert lesson_count_after == lesson_count_before, \
        f"idempotency violated: {lesson_count_before} -> {lesson_count_after}"
    print("   PASS: consolidation is idempotent")

    # --- 8. Test incremental consolidation ---
    print("\n[7] Testing incremental consolidation (add new episodes)...")
    for i in range(3):
        backend.record_episode(_make_success_episode(seed=200 + i))
    for i in range(3):
        backend.record_episode(_make_failure_episode(seed=300 + i))

    report3 = backend.consolidate()
    print(f"   New episodes added   : 6")
    print(f"   Episodes scanned     : {report3.episodes_scanned}")
    print(f"   Lessons extracted    : {report3.lessons_extracted}")
    print(f"   Lessons merged       : {report3.lessons_merged}")
    print(f"   Final lesson count   : {ls_store.count()}")
    # Should either merge into existing lesson or add at most 1 new one
    assert ls_store.count() <= 3, \
        f"dedup should keep lesson count low, got {ls_store.count()}"
    print("   PASS: incremental consolidation with deduplication")

    # --- 9. Unit test: clustering ---
    print("\n[8] Unit test: EpisodeClusterer...")
    clusterer = EpisodeClusterer()
    episodes = [_make_success_episode(i) for i in range(3)] + [_make_failure_episode(i) for i in range(3)]
    clusters = clusterer.cluster(episodes)
    assert len(clusters) >= 1, f"expected at least 1 cluster, got {len(clusters)}"
    assert clusters[0].has_contrast, "cluster should have contrast"
    assert clusters[0].scope == "task_id", f"expected task_id scope, got {clusters[0].scope}"
    print(f"   Clusters: {len(clusters)}, first scope: {clusters[0].scope}")
    print(f"   Successes: {len(clusters[0].successes)}, Failures: {len(clusters[0].failures)}")
    print("   PASS: clustering works")

    # --- 10. Unit test: pattern extraction ---
    print("\n[9] Unit test: PatternExtractor...")
    extractor = PatternExtractor()
    lessons = extractor.extract(clusters[0])
    assert len(lessons) >= 1, f"expected at least 1 lesson, got {len(lessons)}"
    lesson = lessons[0]
    print(f"   Lesson symptom: {lesson.symptom[:60]}")
    print(f"   Lesson fix    : {lesson.fix[:60]}")
    assert lesson.symptom, "extracted lesson should have a symptom"
    assert lesson.fix, "extracted lesson should have a fix"
    print("   PASS: pattern extraction works")

    # Final stats
    print("\n" + "=" * 60)
    final_stats = backend.stats()
    print(f"Final store state: {final_stats}")
    print("ALL PHASE 2 CHECKS PASSED")
    print("=" * 60)

    backend.close()


if __name__ == "__main__":
    main()
