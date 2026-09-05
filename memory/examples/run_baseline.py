"""Produce the TRUE Phase 0 baseline with a real LLM.

Drives the real ReActAgent (backed by OpenRouter or Gemini) over the real task
families, memory-off, across multiple seeds, and reports success and cost
with confidence intervals.

Supported providers:
  - openrouter (default if OPENROUTER_API_KEY is set):
      set OPENROUTER_API_KEY=...
      python -m examples.run_baseline --provider openrouter --model openai/gpt-4o-mini --seeds 5
      python -m examples.run_baseline --provider openrouter --family acme-stream --seeds 15
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path

from lore_memory.agent import GeminiClient, OpenRouterClient, ReActAgent
from lore_memory.backends import NullMemoryBackend
from lore_memory.eval import Harness, Mode, RunConfig
from lore_memory.tasks import load_tasks

TASKS_ROOT = Path(__file__).resolve().parent.parent / "tasks"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5, help="number of seeds (>=5 recommended, 15-20 for tight CI)")
    ap.add_argument(
        "--provider",
        choices=["openrouter", "gemini"],
        default="openrouter" if os.environ.get("OPENROUTER_API_KEY") else "gemini",
        help="LLM provider (default: openrouter if OPENROUTER_API_KEY is set, else gemini)",
    )
    ap.add_argument(
        "--model",
        default=None,
        help="model name (defaults: openai/gpt-4o-mini for openrouter, gemini-2.0-flash-lite for gemini)",
    )
    ap.add_argument("--family", default=None, help="filter tasks by family name (e.g. 'acme-stream')")
    ap.add_argument("--task", default=None, help="filter tasks by task id (e.g. 'acme-stream-consumer')")
    ap.add_argument("--max-steps", type=int, default=12)
    ap.add_argument("--max-tokens", type=int, default=4096, help="max tokens per LLM response")
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
        llm = OpenRouterClient(model=args.model, max_tokens=args.max_tokens)
    else:
        llm = GeminiClient(model=args.model)

    agent = ReActAgent(llm, max_steps=args.max_steps)
    harness = Harness(agent, tasks)
    cfg = RunConfig(seeds=tuple(range(args.seeds)))

    # memory_factory=None -> baseline only. This is the flat line.
    report = harness.run(baseline_factory=NullMemoryBackend, memory_factory=None, config=cfg)

    base = report.per_condition[Mode.BASELINE]

    # --- Per-task breakdown ---
    by_task: dict[str, list[bool]] = defaultdict(list)
    failures: list[dict] = []
    for r in report.records:
        if r.mode == Mode.BASELINE and r.countable:
            by_task[r.task_id].append(r.success)
            if not r.success:
                failures.append({
                    "task_id": r.task_id,
                    "family": r.task_family,
                    "seed": r.seed,
                    "is_control": r.is_control,
                    "detail": r.detail.strip(),
                })

    print("\n" + "=" * 60)
    print(f"=== TRUE Phase 0 Baseline ({args.provider} / {args.model}) ===")
    print("=" * 60)
    print(f"Success rate        : {base.success}")
    print(f"Tokens / success    : {base.tokens_per_success}")
    print(f"Scored attempts     : {base.n_attempts}")
    print(f"Contamination delta : {report.contamination_delta:+.3f}  (flagged={report.contaminated})")

    print("\n--- Per-Task Breakdown ---")
    for tid, results in sorted(by_task.items()):
        pass_count = sum(1 for x in results if x)
        total = len(results)
        rate = pass_count / total if total else 0.0
        print(f"  {tid:25}: {pass_count}/{total} ({rate:.1%})")

    if failures:
        print("\n--- Failure Diagnosis (Examine Gotcha vs Noise) ---")
        for i, f in enumerate(failures, 1):
            ctrl = " [CONTROL]" if f["is_control"] else ""
            print(f"\n[{i}] Task: {f['task_id']}{ctrl} | Seed: {f['seed']}")
            print(f"    Detail: {f['detail'] or '(no error detail captured)'}")
    else:
        print("\n(No failures recorded across all evaluated seeds)")

    print("=" * 60)
    print("\nAnchor every later phase to THIS success rate, not the mock's.")


if __name__ == "__main__":
    main()
