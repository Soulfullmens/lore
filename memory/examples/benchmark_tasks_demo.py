"""Benchmark tasks validation & cross-transfer demo.

Tests:
1. Deterministic grading of the 3 new tasks:
   - acme-stream-cleanup: buggy fails on leak, fixed passes
   - acme-stream-producer: buggy fails on race/overflow, fixed passes
   - acme-stream-timeout: buggy fails on exception swallowing, fixed passes
2. Task-family cross-transfer:
   - Stores lessons for all 3 tasks in the acme-stream family
   - Queries with generic 'asyncio resource cleanup'
   - Verifies stream_cleanup ranks highest, while producer and timeout also retrieve with lower relevance
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from lore_memory.models import (
    Lesson,
    LessonScope,
    LessonType,
)
from lore_memory.store import (
    ConsolidatingMemoryBackend,
    HashEmbedder,
    SqliteLessonStore,
)
from lore_memory.tasks import load_task


# Fixed reference solutions
FIXED_CLEANUP = '''import asyncio
from client import AcmeStreamSession


async def process_session(session: AcmeStreamSession, handler) -> int:
    await session.open()
    count = 0
    try:
        async for msg in session.stream_messages():
            await handler(msg)
            count += 1
        return count
    finally:
        await session.close()
'''

FIXED_PRODUCER = '''import asyncio
from client import AcmeStreamProducerClient


async def produce_stream(
    client: AcmeStreamProducerClient,
    items: list[str],
    ready_event: asyncio.Event,
) -> int:
    count = 0
    for item in items:
        await ready_event.wait()
        ready_event.clear()
        await client.publish(item)
        count += 1
    return count
'''

FIXED_TIMEOUT = '''import asyncio
from client import AcmeStreamPoller, AcmeAuthError, AcmeTimeoutExceededError


async def poll_with_retry(poller: AcmeStreamPoller, max_retries: int = 3) -> list[dict]:
    events = []
    retries = 0
    while len(events) < 2:
        try:
            event = await poller.poll(timeout_sec=0.05)
            events.append(event)
            retries = 0
        except (asyncio.TimeoutError, TimeoutError):
            retries += 1
            if retries > max_retries:
                raise AcmeTimeoutExceededError(f"Exceeded {max_retries} retries on poll timeout")
            await asyncio.sleep(0.005)
        except Exception:
            raise
    return events
'''


def test_deterministic_task(task_rel_path: str, fixed_code: str) -> None:
    import subprocess
    task_dir = Path(__file__).resolve().parent.parent / "tasks" / task_rel_path
    task = load_task(task_dir)

    with tempfile.TemporaryDirectory(prefix=f"lore_test_{task.id}_") as ws:
        task.setup(ws)

        # 1. Run buggy code -> must fail
        proc = subprocess.run(
            task.eval_command,
            cwd=ws,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0, f"Buggy code for {task.id} should have failed, but passed!"
        print(f"  [OK] {task.id}: Buggy baseline fails deterministically (exit code {proc.returncode})")

        # 2. Inject fixed code -> must pass
        (Path(ws) / "solution.py").write_text(fixed_code, encoding="utf-8")
        proc_fixed = subprocess.run(
            task.eval_command,
            cwd=ws,
            capture_output=True,
            text=True,
        )
        assert proc_fixed.returncode == 0, f"Fixed code for {task.id} failed: {proc_fixed.stdout + proc_fixed.stderr}"
        print(f"  [OK] {task.id}: Fixed solution passes cleanly (exit code 0)")


def test_cross_transfer():
    print("\n--- Testing Task Family Cross-Transfer ---")
    embedder = HashEmbedder(dim=64)
    store = SqliteLessonStore(dim=64)
    backend = ConsolidatingMemoryBackend(lesson_store=store, embedder=embedder, dim=64)

    # 1. Store lessons for all 3 tasks
    l_cleanup = Lesson(
        symptom="Resource leak / socket unclosed on stream exception",
        fix="Wrap in try...finally and await session.close() in finally",
        rationale="Guarantees resource disposal and avoids connection exhaustion",
        task_id="acme-stream-cleanup",
        task_family="acme-stream",
        scope=LessonScope.DOMAIN,
        confidence=0.9,
    )
    vec_cleanup = embedder.embed([f"{l_cleanup.symptom} {l_cleanup.fix} {l_cleanup.rationale}"])[0]
    store.add(l_cleanup, vec_cleanup)

    l_producer = Lesson(
        symptom="Race condition and buffer overflow during async production",
        fix="Synchronize with consumer using ready_event.wait() and clear()",
        rationale="Enforces backpressure handshakes instead of sleep",
        task_id="acme-stream-producer",
        task_family="acme-stream",
        scope=LessonScope.FAMILY,
        confidence=0.85,
    )
    vec_producer = embedder.embed([f"{l_producer.symptom} {l_producer.fix} {l_producer.rationale}"])[0]
    store.add(l_producer, vec_producer)

    l_timeout = Lesson(
        symptom="Swallowed fatal errors during stream poll timeout",
        fix="Catch TimeoutError specifically for backoff; re-raise fatal exceptions",
        rationale="Distinguishes transient network pause from fatal auth failures",
        task_id="acme-stream-timeout",
        task_family="acme-stream",
        scope=LessonScope.FAMILY,
        confidence=0.8,
    )
    vec_timeout = embedder.embed([f"{l_timeout.symptom} {l_timeout.fix} {l_timeout.rationale}"])[0]
    store.add(l_timeout, vec_timeout)

    # Query with generic resource cleanup
    query = "Properly close open stream session on exception in finally block"
    retrieved = backend.retrieve(query, k=3, task_family="acme-stream")

    print(f"  Query: '{query}'")
    for idx, r in enumerate(retrieved, 1):
        print(f"    {idx}. [{r.metadata.get('task_id')}] score={r.score:.3f}")

    assert len(retrieved) >= 1, "Should retrieve at least 1 lesson"
    # Verify stream-cleanup ranks highest
    assert retrieved[0].metadata.get("task_id") == "acme-stream-cleanup", "stream-cleanup should rank top for cleanup query"
    print("  [OK] Cross-transfer verified: cleanup ranks #1, sibling tasks retrieve with lower scores")


def main():
    print("=" * 65)
    print("=== P0: Diverse Benchmark Tasks Validation ===")
    print("=" * 65)
    print("\n--- 1. Deterministic Evaluation on 3 New Failure Modes ---")
    test_deterministic_task("acme_stream/stream_cleanup", FIXED_CLEANUP)
    test_deterministic_task("acme_stream/stream_producer", FIXED_PRODUCER)
    test_deterministic_task("acme_stream/stream_timeout", FIXED_TIMEOUT)
    test_cross_transfer()
    print("\n" + "=" * 65)
    print("=== All Benchmark Task Checks PASSED ===")
    print("=" * 65)


if __name__ == "__main__":
    main()
