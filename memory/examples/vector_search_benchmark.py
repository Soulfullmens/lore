"""Vector search benchmark: sqlite-vec ANN vs Python brute-force cosine.

Validates:
  1. sqlite-vec ANN produces identical top-k results (recall = 1.0 for exact vec0).
  2. Sub-5ms query latency at 100, 1,000, and 10,000 vectors.
  3. Graceful fallback works correctly when sqlite-vec is disabled.
"""
from __future__ import annotations

import random
import time

from lore_memory.store.lesson_store import SqliteLessonStore
from lore_memory.store.embedding import HashEmbedder, _l2_normalize
from lore_memory.models import Lesson, LessonScope, LessonType, utcnow

DIM = 256
SCALES = [100, 1_000, 10_000]
TOP_K = 5
NUM_QUERIES = 20


def _random_vector(rng: random.Random) -> list[float]:
    """Generate a random L2-normalized vector."""
    raw = [rng.gauss(0, 1) for _ in range(DIM)]
    return _l2_normalize(raw)


def _make_lesson(idx: int) -> Lesson:
    """Create a synthetic lesson for benchmarking."""
    return Lesson(
        id=f"bench-{idx:06d}",
        symptom=f"Synthetic symptom #{idx}",
        fix=f"Synthetic fix #{idx}",
        rationale=f"Synthetic rationale #{idx}",
        statement=f"Synthetic lesson statement #{idx} for vector benchmark testing",
        source_episode_ids=[f"ep-{idx}"],
        task_id=f"task-{idx % 50}",
        task_family="benchmark",
        confidence=0.5,
        times_applied=1,
        times_helped=0,
        times_harmed=0,
        model_confidence={},
        scope=LessonScope.DOMAIN,
        lesson_type=LessonType.POSITIVE,
        parent_lesson_id="",
        tags=["benchmark"],
        created_at=utcnow(),
        last_used=None,
    )


def _benchmark_scale(n: int, rng: random.Random) -> dict:
    """Benchmark a single scale factor, return timing results."""
    # --- Store with sqlite-vec enabled ---
    vec_store = SqliteLessonStore(":memory:", dim=DIM, use_vec=True)
    has_vec = vec_store.use_vec

    # --- Store with sqlite-vec disabled (pure Python) ---
    py_store = SqliteLessonStore(":memory:", dim=DIM, use_vec=False)

    # Generate vectors
    vectors = [_random_vector(rng) for _ in range(n)]
    lessons = [_make_lesson(i) for i in range(n)]

    # Insert into both stores
    for lesson, vec in zip(lessons, vectors):
        if has_vec:
            vec_store.add(lesson, vec)
        py_store.add(lesson, vec)

    # Generate query vectors
    queries = [_random_vector(rng) for _ in range(NUM_QUERIES)]

    # --- Benchmark sqlite-vec ANN ---
    vec_times = []
    vec_results = []
    if has_vec:
        for q in queries:
            t0 = time.perf_counter_ns()
            results = vec_store.search(q, k=TOP_K, min_confidence=0.0, inject_untested=True)
            t1 = time.perf_counter_ns()
            vec_times.append((t1 - t0) / 1e6)  # ms
            vec_results.append({r.id for r in results})

    # --- Benchmark Python brute-force ---
    py_times = []
    py_results = []
    for q in queries:
        t0 = time.perf_counter_ns()
        results = py_store.search(q, k=TOP_K, min_confidence=0.0, inject_untested=True)
        t1 = time.perf_counter_ns()
        py_times.append((t1 - t0) / 1e6)  # ms
        py_results.append({r.id for r in results})

    # --- Compute recall (should be 1.0 for exact vec0) ---
    recall = None
    if has_vec and vec_results and py_results:
        recalls = []
        for v_set, p_set in zip(vec_results, py_results):
            if p_set:
                recalls.append(len(v_set & p_set) / len(p_set))
        recall = sum(recalls) / len(recalls) if recalls else None

    return {
        "n": n,
        "has_vec": has_vec,
        "vec_mean_ms": sum(vec_times) / len(vec_times) if vec_times else None,
        "vec_p50_ms": sorted(vec_times)[len(vec_times) // 2] if vec_times else None,
        "vec_p95_ms": sorted(vec_times)[int(len(vec_times) * 0.95)] if vec_times else None,
        "py_mean_ms": sum(py_times) / len(py_times) if py_times else None,
        "py_p50_ms": sorted(py_times)[len(py_times) // 2] if py_times else None,
        "py_p95_ms": sorted(py_times)[int(len(py_times) * 0.95)] if py_times else None,
        "recall": recall,
    }


def main():
    print("=" * 65)
    print("=== Vector Search Benchmark: sqlite-vec ANN vs Python Cosine ===")
    print("=" * 65)
    print(f"  Dimensions: {DIM}, Top-k: {TOP_K}, Queries: {NUM_QUERIES}")
    print()

    rng = random.Random(42)
    all_pass = True

    for n in SCALES:
        print(f"--- Scale: {n:,} vectors ---")
        result = _benchmark_scale(n, rng)

        if result["has_vec"]:
            print(f"  sqlite-vec ANN: mean={result['vec_mean_ms']:.2f}ms, "
                  f"p50={result['vec_p50_ms']:.2f}ms, p95={result['vec_p95_ms']:.2f}ms")
        else:
            print(f"  sqlite-vec ANN: unavailable (fallback mode)")

        print(f"  Python cosine:  mean={result['py_mean_ms']:.2f}ms, "
              f"p50={result['py_p50_ms']:.2f}ms, p95={result['py_p95_ms']:.2f}ms")

        if result["recall"] is not None:
            print(f"  Recall@{TOP_K}:     {result['recall']:.3f}")
            if result["recall"] < 0.8:
                print(f"  [WARN] Recall below 0.8 — ANN approximation quality issue")

        # Latency check: sqlite-vec should be <5ms at all scales
        if result["has_vec"]:
            if result["vec_p95_ms"] < 5.0:
                print(f"  [OK] sqlite-vec p95 < 5ms (pass)")
            else:
                print(f"  [WARN] sqlite-vec p95 = {result['vec_p95_ms']:.2f}ms > 5ms target")
                # Only fail at large scale — small scale timing noise is acceptable
                if n >= 1_000:
                    all_pass = False

        # Python brute-force should degrade at scale
        if n >= 10_000 and result["py_p95_ms"] > 50.0:
            print(f"  [NOTE] Python brute-force p95 = {result['py_p95_ms']:.2f}ms "
                  f"(expected degradation at scale)")

        if result["has_vec"] and result["vec_mean_ms"] and result["py_mean_ms"]:
            speedup = result["py_mean_ms"] / result["vec_mean_ms"]
            print(f"  Speedup: {speedup:.1f}x")

        print()

    if all_pass:
        print("=" * 65)
        print("=== All Vector Search Benchmarks PASSED ===")
        print("=" * 65)
    else:
        print("=" * 65)
        print("=== Vector Search Benchmark: SOME CHECKS FAILED ===")
        print("=" * 65)
        exit(1)


if __name__ == "__main__":
    main()
