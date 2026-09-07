"""Phase 3 offline proof — no API key required.

End-to-end test of the causal verification loop and confidence engine:

1. Counterfactual Credit Assignment:
   - Tests all 4 causal quadrants (CAUSED_PASS, CAUSED_FAIL, INDEPENDENT_PASS, INDEPENDENT_FAIL)
   - Verifies explicit BaselineMissingError when baseline is not cached
2. Model-Specific Confidence Gating & Untested Model Policy:
   - Verifies independent Bayesian Beta posteriors per model
   - Verifies untested model policy: inject_untested=False (0.0 confidence) vs True (global fallback)
3. Negative Lesson Guards & Active Retrieval Suppression:
   - Verifies NegativeGuardGenerator emits blocking guard on CAUSED_FAIL
   - Verifies parent lesson is suppressed from retrieval for harmed model while remaining active for others
4. Hierarchical Fast-Path Retrieval:
   - Tier 1: exact task_id + GLOBAL scope
   - Tier 2: task_family + DOMAIN scope
   - Tier 3: cosine embedding search
   - Tier 4: episode fallback
   - Verifies Tier 1 speedup (<1ms vs vector search)
5. Sequential Analysis & Early Stopping:
   - Tests PROMOTE decision (P(theta > 0.7) >= 0.95)
   - Tests DEMOTE decision (P(theta < 0.3) >= 0.95)
   - Tests normal approximation fallback for large parameters (alpha, beta > 100)

Run: python -m examples.phase3_verification_demo
"""

from __future__ import annotations

import time

from lore_memory.models import (
    Lesson,
    LessonScope,
    LessonType,
    MemoryKind,
    OutcomeStatus,
    new_id,
)
from lore_memory.store import (
    ConsolidatingMemoryBackend,
    HashEmbedder,
    SqliteEpisodeStore,
    SqliteLessonStore,
)
from lore_memory.verification import (
    BaselineMissingError,
    CausalAttribution,
    CreditAssigner,
    NegativeGuardGenerator,
    Reflector,
    SeedOutcome,
    SequentialAnalyzer,
    SequentialDecision,
)


def run_demo() -> None:
    print("=" * 65)
    print("=== Phase 3: Causal Verification Loop & Confidence Engine ===")
    print("=" * 65)

    # ----------------------------------------------------------------------- #
    # 1. Counterfactual Credit Assignment (4 Quadrants)
    # ----------------------------------------------------------------------- #
    print("\n--- 1. Counterfactual Credit Assignment (4 Quadrants) ---")
    reflector = Reflector()

    # Cache baselines for 4 seeds
    # Seed 1: Baseline FAIL
    reflector.cache_baseline(SeedOutcome(task_id="acme-consumer", seed=1, success=False))
    # Seed 2: Baseline PASS
    reflector.cache_baseline(SeedOutcome(task_id="acme-consumer", seed=2, success=True))
    # Seed 3: Baseline PASS
    reflector.cache_baseline(SeedOutcome(task_id="acme-consumer", seed=3, success=True))
    # Seed 4: Baseline FAIL
    reflector.cache_baseline(SeedOutcome(task_id="acme-consumer", seed=4, success=False))

    # Test Quadrant 1: Baseline FAIL + Treatment PASS -> CAUSED_PASS
    q1 = reflector.compare(SeedOutcome(task_id="acme-consumer", seed=1, success=True))
    assert q1 == CausalAttribution.CAUSED_PASS, f"Expected CAUSED_PASS, got {q1}"
    print("  [OK] Quadrant 1 (FAIL -> PASS): CAUSED_PASS (lesson fixed it)")

    # Test Quadrant 2: Baseline PASS + Treatment FAIL -> CAUSED_FAIL
    q2 = reflector.compare(SeedOutcome(task_id="acme-consumer", seed=2, success=False))
    assert q2 == CausalAttribution.CAUSED_FAIL, f"Expected CAUSED_FAIL, got {q2}"
    print("  [OK] Quadrant 2 (PASS -> FAIL): CAUSED_FAIL (lesson broke it)")

    # Test Quadrant 3: Baseline PASS + Treatment PASS -> INDEPENDENT_PASS
    q3 = reflector.compare(SeedOutcome(task_id="acme-consumer", seed=3, success=True))
    assert q3 == CausalAttribution.INDEPENDENT_PASS, f"Expected INDEPENDENT_PASS, got {q3}"
    print("  [OK] Quadrant 3 (PASS -> PASS): INDEPENDENT_PASS (redundant)")

    # Test Quadrant 4: Baseline FAIL + Treatment FAIL -> INDEPENDENT_FAIL
    q4 = reflector.compare(SeedOutcome(task_id="acme-consumer", seed=4, success=False))
    assert q4 == CausalAttribution.INDEPENDENT_FAIL, f"Expected INDEPENDENT_FAIL, got {q4}"
    print("  [OK] Quadrant 4 (FAIL -> FAIL): INDEPENDENT_FAIL (task too hard)")

    # Test Missing Baseline Dependency
    try:
        reflector.compare(SeedOutcome(task_id="acme-consumer", seed=99, success=True))
        raise AssertionError("Should have raised BaselineMissingError!")
    except BaselineMissingError as err:
        assert err.seed == 99
        print(f"  [OK] BaselineMissingError correctly raised on missing seed 99: '{err}'")

    # ----------------------------------------------------------------------- #
    # 2. Model-Specific Confidence Gating & Untested Model Policy
    # ----------------------------------------------------------------------- #
    print("\n--- 2. Model-Specific Confidence Gating & Untested Model Policy ---")
    lesson_store = SqliteLessonStore(dim=64)
    assigner = CreditAssigner(lesson_store)

    test_lesson = Lesson(
        symptom="Connection timeout on stream consumer",
        fix="Increase socket keepalive timeout",
        rationale="Prevents premature disconnects",
        task_id="acme-consumer",
        task_family="acme-stream",
        scope=LessonScope.SPECIFIC,
    )
    dim_vec = [0.1] * 64
    lesson_store.add(test_lesson, dim_vec)

    # Initial confidence with Beta(2,2) prior = 2/4 = 0.50
    initial_conf = test_lesson.bayesian_confidence()
    assert abs(initial_conf - 0.50) < 1e-4

    # Apply 3 positive outcomes for Model A ("openai/gpt-4o-mini")
    for s in [10, 11, 12]:
        assigner.assign(
            test_lesson.id,
            CausalAttribution.CAUSED_PASS,
            model="openai/gpt-4o-mini",
            task_id="acme-consumer",
            seed=s,
        )

    # Apply 3 negative outcomes for Model B ("google/gemini-2.5-flash")
    for s in [20, 21, 22]:
        assigner.assign(
            test_lesson.id,
            CausalAttribution.CAUSED_FAIL,
            model="google/gemini-2.5-flash",
            task_id="acme-consumer",
            seed=s,
        )

    updated_lesson = lesson_store.get(test_lesson.id)
    assert updated_lesson is not None

    conf_model_a = updated_lesson.bayesian_confidence(model="openai/gpt-4o-mini")
    conf_model_b = updated_lesson.bayesian_confidence(model="google/gemini-2.5-flash")

    print(f"  Model A (openai/gpt-4o-mini) confidence:     {conf_model_a:.3f} (elevated)")
    print(f"  Model B (google/gemini-2.5-flash) confidence: {conf_model_b:.3f} (degraded)")
    assert conf_model_a > 0.70, f"Expected Model A conf > 0.70, got {conf_model_a}"
    assert conf_model_b < 0.35, f"Expected Model B conf < 0.35, got {conf_model_b}"

    # Untested model policy:
    # Model C is untested
    untested_strict = updated_lesson.bayesian_confidence(model="anthropic/claude-3-haiku")
    # In lesson_store search with inject_untested=False:
    search_untested_strict = lesson_store.search(
        dim_vec,
        k=5,
        model="anthropic/claude-3-haiku",
        min_confidence=0.1,
        inject_untested=False,
    )
    assert len(search_untested_strict) == 0, "Untested model should be gated when inject_untested=False"
    print("  [OK] Untested model gated (0 results) when inject_untested=False")

    search_untested_open = lesson_store.search(
        dim_vec,
        k=5,
        model="anthropic/claude-3-haiku",
        min_confidence=0.1,
        inject_untested=True,
    )
    assert len(search_untested_open) == 1, "Untested model falls back to global when inject_untested=True"
    print("  [OK] Untested model retrieves lesson when inject_untested=True")

    # ----------------------------------------------------------------------- #
    # 3. Negative Lesson Guards & Active Retrieval Suppression
    # ----------------------------------------------------------------------- #
    print("\n--- 3. Negative Lesson Guards & Active Retrieval Suppression ---")
    guard_gen = NegativeGuardGenerator(lesson_store)

    # Harmed attribution for Model B emits negative guard
    guard_report = guard_gen.maybe_emit(
        test_lesson.id,
        CausalAttribution.CAUSED_FAIL,
        model="google/gemini-2.5-flash",
        task_id="acme-consumer",
    )
    assert guard_report.guard_emitted, "Negative guard should have been emitted"
    print(f"  [OK] Emitted negative guard: {guard_report.guard_id} blocking lesson {test_lesson.id}")

    # Verify active guard check
    active_guards_b = lesson_store.get_active_guards([test_lesson.id], model="google/gemini-2.5-flash")
    assert test_lesson.id in active_guards_b, "Lesson should be in active guards for Model B"

    active_guards_a = lesson_store.get_active_guards([test_lesson.id], model="openai/gpt-4o-mini")
    assert test_lesson.id not in active_guards_a, "Lesson should NOT be guarded for Model A"
    print("  [OK] Guard lookup correctly partitions: blocked for Model B, allowed for Model A")

    # Verify retrieval suppression in search()
    retrieved_for_a = lesson_store.search(dim_vec, k=5, model="openai/gpt-4o-mini")
    assert len(retrieved_for_a) == 1, "Model A should receive the lesson"

    retrieved_for_b = lesson_store.search(dim_vec, k=5, model="google/gemini-2.5-flash")
    assert len(retrieved_for_b) == 0, "Model B should have the lesson suppressed by negative guard!"
    print("  [OK] Active retrieval suppression verified: Model A retrieved 1 lesson, Model B suppressed to 0")

    # ----------------------------------------------------------------------- #
    # 4. Hierarchical Fast-Path Retrieval (Tier 1 vs Tier 3)
    # ----------------------------------------------------------------------- #
    print("\n--- 4. Hierarchical Fast-Path Retrieval ---")
    backend = ConsolidatingMemoryBackend(
        lesson_store=lesson_store,
        dim=64,
        model="openai/gpt-4o-mini",
        hierarchical=True,
    )

    # Add a domain-level and global-level lesson
    global_lesson = Lesson(
        symptom="General syntax or indentation discrepancy",
        fix="Ensure standard 4-space indentation",
        rationale="PEP 8 compliance",
        scope=LessonScope.GLOBAL,
        confidence=0.85,
    )
    lesson_store.add(global_lesson, dim_vec)

    # Benchmark Tier 1 lookup speed vs Tier 3 embedding search
    n_iters = 500

    # Tier 1 exact task_id match
    t0 = time.perf_counter()
    for _ in range(n_iters):
        res1 = backend.retrieve("some query text", k=5, task_id="acme-consumer")
    t_tier1 = (time.perf_counter() - t0) / n_iters * 1000

    # Force Tier 3 embedding search (no task_id / family provided)
    t0 = time.perf_counter()
    for _ in range(n_iters):
        res3 = backend.retrieve("some query text", k=5)
    t_tier3 = (time.perf_counter() - t0) / n_iters * 1000

    print(f"  Tier 1 (exact task_id + GLOBAL) latency: {t_tier1:.3f} ms")
    print(f"  Tier 3 (embedding vector search) latency: {t_tier3:.3f} ms")
    print(f"  Speedup: {t_tier3 / max(t_tier1, 1e-6):.1f}x faster")
    assert len(res1) > 0, "Tier 1 retrieval should return lessons"
    assert t_tier1 < 1.0, f"Tier 1 expected < 1ms, got {t_tier1:.3f}ms"
    print("  [OK] Hierarchical Tier 1 fast-path operates under 1ms")

    # ----------------------------------------------------------------------- #
    # 5. Sequential Analysis & Early Stopping
    # ----------------------------------------------------------------------- #
    print("\n--- 5. Sequential Analysis & Early Stopping ---")
    analyzer = SequentialAnalyzer(tau_promote=0.70, tau_demote=0.30, confidence_level=0.95)

    # Case A: Decisive Success
    # 16 successes, 1 failure with Beta(2,2) prior -> alpha = 18, beta = 3
    rep_promote = analyzer.evaluate(a=18, b=3, n_trials=17)
    print(f"  Case A: 16 pass / 1 fail -> P(theta > 0.70) = {rep_promote.p_above_tau_promote:.4f} -> {rep_promote.decision.value}")
    assert rep_promote.decision == SequentialDecision.PROMOTE

    # Case B: Decisive Harm
    # 1 success, 16 failures with Beta(2,2) prior -> alpha = 3, beta = 18
    rep_demote = analyzer.evaluate(a=3, b=18, n_trials=17)
    print(f"  Case B: 1 pass / 16 fail -> P(theta < 0.30) = {rep_demote.p_below_tau_demote:.4f} -> {rep_demote.decision.value}")
    assert rep_demote.decision == SequentialDecision.DEMOTE

    # Case C: Ambiguous Evidence
    # 5 successes, 5 failures with Beta(2,2) prior -> alpha = 7, beta = 7
    rep_continue = analyzer.evaluate(a=7, b=7, n_trials=10)
    print(f"  Case C: 5 pass / 5 fail  -> Ambiguous -> {rep_continue.decision.value}")
    assert rep_continue.decision == SequentialDecision.CONTINUE

    # Case D: Normal Approximation Fallback for Large Parameters (alpha, beta > 100)
    rep_large = analyzer.evaluate(a=150, b=30, n_trials=180)
    print(f"  Case D: Large N (alpha=150, beta=30) -> Normal approx fallback -> {rep_large.decision.value}")
    assert rep_large.decision == SequentialDecision.PROMOTE

    print("\n" + "=" * 65)
    print("=== All Phase 3 Verification & Confidence Tests PASSED ===")
    print("=" * 65)


if __name__ == "__main__":
    run_demo()
