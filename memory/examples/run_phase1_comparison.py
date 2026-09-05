"""Compare Memory-OFF (baseline) vs Memory-ON (Phase 1 episodic memory).

Runs the multi-seed Harness over both conditions with a real LLM (OpenRouter or Gemini),
computing:
  1. Success rate lift (Memory vs Baseline)
  2. Same-Seed Paired Flips Analysis (Rescues: Fail->Pass vs Regressions: Pass->Fail)
  3. Tokens per success (cost efficiency)
  4. Contamination check on control tasks
  5. Causal ablation delta (withholding injected episodes)

Usage with OpenRouter:
    set OPENROUTER_API_KEY=...
    python -m examples.run_phase1_comparison --provider openrouter --model openai/gpt-4o-mini --family acme-stream --seeds 15
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path

from lore_memory.agent import GeminiClient, OpenRouterClient, ReActAgent
from lore_memory.backends import NullMemoryBackend
from lore_memory.eval import AblationConfig, Harness, Mode, RunConfig
from lore_memory.store import EpisodicMemoryBackend, HashEmbedder
from lore_memory.tasks import load_tasks

TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5, help="number of seeds (15-20 recommended for tight evaluation)")
    ap.add_argument(
        "--provider",
        choices=["openrouter", "gemini"],
        default="openrouter" if os.environ.get("OPENROUTER_API_KEY") else "gemini",
        help="LLM provider",
    )
    ap.add_argument("--model", default=None, help="LLM model name")
    ap.add_argument("--family", default=None, help="filter tasks by family name (e.g. 'acme-stream')")
    ap.add_argument("--task", default=None, help="filter tasks by task id")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--k", type=int, default=3, help="memories retrieved per task")
    ap.add_argument("--ablate", action="store_true", default=True, help="enable leave-one-out causal ablation")
    args = ap.parse_args()

    if args.model is None:
        args.model = "openai/gpt-4o-mini" if args.provider == "openrouter" else "gemini-2.0-flash-lite"

    tasks = load_tasks(TASKS_ROOT)
    if not tasks:
        raise SystemExit(f"no tasks found under {TASKS_ROOT}")

    if args.family:
        tasks = [t for t in tasks if t.family == args.family or t.is_control]
    if args.task:
        tasks = [t for t in tasks if t.id == args.task or t.is_control]

    families = sorted({t.family for t in tasks})
    print(f"Loaded {len(tasks)} tasks across families: {families}")
    print(f"Provider: {args.provider} | Model: {args.model} | Seeds: {args.seeds}")

    if args.provider == "openrouter":
        llm = OpenRouterClient(model=args.model)
    else:
        llm = GeminiClient(model=args.model)

    agent = ReActAgent(llm, max_steps=args.max_steps, retrieve_k=args.k)
    harness = Harness(agent, tasks)

    def memory_factory():
        emb = HashEmbedder(dim=256)
        return EpisodicMemoryBackend(embedder=emb)

    cfg = RunConfig(
        seeds=tuple(range(args.seeds)),
        k=args.k,
        ablation=AblationConfig(enabled=args.ablate, sample_rate=0.5, max_memories=3),
    )

    print(f"\nRunning benchmark comparison across {args.seeds} seeds...")
    report = harness.run(
        baseline_factory=NullMemoryBackend,
        memory_factory=memory_factory,
        config=cfg,
    )

    base = report.per_condition.get(Mode.BASELINE)
    mem = report.per_condition.get(Mode.MEMORY)

    print("\n" + "=" * 60)
    print(f"=== Phase 1 Comparison Report ({args.provider} / {args.model}) ===")
    print("=" * 60)
    if base:
        print(f"BASELINE Success Rate : {base.success}")
        print(f"BASELINE Tokens/Succ  : {base.tokens_per_success}")
        print(f"BASELINE Attempts     : {base.n_attempts}")
    if mem:
        print(f"\nMEMORY Success Rate   : {mem.success}")
        print(f"MEMORY Tokens/Succ    : {mem.tokens_per_success}")
        print(f"MEMORY Attempts       : {mem.n_attempts}")

    lift = report.improvement()
    if lift is not None:
        print(f"\nOverall Lift (Mem - Base): {lift:+.3f}")
    print(f"Contamination delta      : {report.contamination_delta:+.3f}  (flagged={report.contaminated})")

    # --- Per-task comparison ---
    base_by_task: dict[str, list[bool]] = defaultdict(list)
    mem_by_task: dict[str, list[bool]] = defaultdict(list)
    base_results_map: dict[tuple[str, int], bool] = {}
    mem_results_map: dict[tuple[str, int], bool] = {}

    for r in report.records:
        if not r.countable:
            continue
        key = (r.task_id, r.seed)
        if r.mode == Mode.BASELINE:
            base_by_task[r.task_id].append(r.success)
            base_results_map[key] = r.success
        elif r.mode == Mode.MEMORY:
            mem_by_task[r.task_id].append(r.success)
            mem_results_map[key] = r.success

    print("\n--- Per-Task Performance (Baseline -> Memory) ---")
    for tid in sorted(base_by_task.keys()):
        b_passes = sum(1 for x in base_by_task[tid] if x)
        b_tot = len(base_by_task[tid])
        b_rate = b_passes / b_tot if b_tot else 0.0

        m_passes = sum(1 for x in mem_by_task.get(tid, []) if x)
        m_tot = len(mem_by_task.get(tid, []))
        m_rate = m_passes / m_tot if m_tot else 0.0
        delta = m_rate - b_rate
        print(f"  {tid:25}: {b_passes}/{b_tot} ({b_rate:.0%}) -> {m_passes}/{m_tot} ({m_rate:.0%})  [Δ={delta:+.0%}]")

    # --- Paired Flips Analysis ---
    rescues = []      # Fail in baseline -> Pass in memory
    regressions = []  # Pass in baseline -> Fail in memory
    stable_pass = 0
    stable_fail = 0

    for key, b_succ in base_results_map.items():
        if key in mem_results_map:
            m_succ = mem_results_map[key]
            tid, seed = key
            if not b_succ and m_succ:
                rescues.append((tid, seed))
            elif b_succ and not m_succ:
                regressions.append((tid, seed))
            elif b_succ and m_succ:
                stable_pass += 1
            else:
                stable_fail += 1

    print("\n--- Same-Seed Paired Flips Analysis ---")
    print(f"  Rescues (FAIL -> PASS)      : {len(rescues)}")
    for tid, seed in rescues:
        print(f"    + Rescued: {tid} (seed={seed})")
    print(f"  Regressions (PASS -> FAIL)  : {len(regressions)}")
    for tid, seed in regressions:
        print(f"    - Regressed: {tid} (seed={seed})")
    print(f"  Stable Passes (PASS -> PASS): {stable_pass}")
    print(f"  Stable Fails (FAIL -> FAIL) : {stable_fail}")
    net_flips = len(rescues) - len(regressions)
    print(f"  Net Paired Flip Delta       : {net_flips:+d}")

    # --- Ablation Analysis ---
    print(f"\n--- Causal Ablation Signal ---")
    print(f"Ablation attempts probed : {len(report.ablation)}")
    if report.ablation:
        helpful = [a for a in report.ablation if a.delta > 0]
        neutral = [a for a in report.ablation if a.delta == 0]
        harmful = [a for a in report.ablation if a.delta < 0]
        print(f"  - Causally helpful (withholding hurt) : {len(helpful)}")
        print(f"  - Neutral                             : {len(neutral)}")
        print(f"  - Harmful                             : {len(harmful)}")

    print("=" * 60)


if __name__ == "__main__":
    main()
